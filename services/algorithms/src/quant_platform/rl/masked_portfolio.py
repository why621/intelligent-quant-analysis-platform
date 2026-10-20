"""EarnMore-inspired research networks, deliberately separate from production bundles.

No asset identifiers or slot positions enter the policy. Asset IDs are used only
as decoder queries in the training-only masked reconstruction task. This is a
feature reconstruction adaptation, not the paper's raw-price temporal MAE.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from quant_platform.rl.features import FEATURE_COLUMNS
from quant_platform.rl.portfolio_features import MAX_ASSETS, OBSERVATION_SIZE, SLOT_SIZE

FEATURES = len(FEATURE_COLUMNS)
ARCHITECTURE = "masked-set-sac-research-v1"
VARIANTS = ("mlp", "attention", "masked_attention")


def unpack(observation):
    if observation.ndim != 2 or observation.shape[-1] != OBSERVATION_SIZE:
        raise ValueError("expected batched joint observations")
    if not torch.isfinite(observation).all():
        raise ValueError("nonfinite observation")
    slots = observation[:, :-1].reshape(-1, MAX_ASSETS, SLOT_SIZE)
    active = slots[:, :, -1]
    if not ((active == 0) | (active == 1)).all() or (active.sum(1) < 2).any():
        raise ValueError("expected at least two active assets and binary masks")
    return slots[:, :, :FEATURES], slots[:, :, -2], active.bool(), observation[:, -1:]


class SetEncoder(nn.Module):
    def __init__(self, width=32):
        super().__init__()
        self.project = nn.Linear(FEATURES, width)
        self.cash_token = nn.Parameter(torch.zeros(1, 1, width))
        layer = nn.TransformerEncoderLayer(
            width, 4, width * 2, dropout=0, batch_first=True, norm_first=True
        )
        self.attention = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)

    def forward(self, features, visible):
        # Mask before projection as well as attention: hidden values cannot leak.
        safe = torch.where(visible.unsqueeze(-1), features, 0)
        tokens = self.project(safe)
        tokens = torch.cat((tokens, self.cash_token.expand(len(tokens), -1, -1)), 1)
        mask = torch.cat((visible, torch.ones_like(visible[:, :1])), 1)
        encoded = self.attention(tokens, src_key_padding_mask=~mask)
        return encoded, mask


class MLPEncoder(nn.Module):
    """Fixed-slot joint baseline; deliberately not permutation equivariant."""

    def __init__(self, width):
        super().__init__()
        self.width = width
        self.layers = nn.Sequential(
            nn.Linear(MAX_ASSETS * (FEATURES + 1), 64), nn.ReLU(),
            nn.Linear(64, (MAX_ASSETS + 1) * width),
        )

    def forward(self, features, visible):
        safe = torch.where(visible.unsqueeze(-1), features, 0)
        inputs = torch.cat((safe, visible.unsqueeze(-1)), -1).flatten(1)
        encoded = self.layers(inputs).reshape(-1, MAX_ASSETS + 1, self.width)
        mask = torch.cat((visible, torch.ones_like(visible[:, :1])), 1)
        return encoded, mask


class MaskedSACNetwork(nn.Module):
    def __init__(self, training_assets, width=32, variant="masked_attention"):
        super().__init__()
        if training_assets < 2:
            raise ValueError("need at least two training assets")
        self.width = width
        self.training_assets = training_assets
        if variant not in VARIANTS:
            raise ValueError("unknown architecture variant")
        self.variant = variant
        self.encoder = MLPEncoder(width) if variant == "mlp" else SetEncoder(width)
        self.actor = nn.Sequential(nn.Linear(width + 1, width), nn.SiLU(), nn.Linear(width, 2))
        self.q1 = self._critic(width)
        self.q2 = self._critic(width)
        self.mask_token = nn.Parameter(torch.zeros(1, 1, width))
        self.decoder_queries = nn.Embedding(training_assets, width)
        self.decoder_attention = nn.MultiheadAttention(width, 4, batch_first=True)
        self.decoder = nn.Linear(width, FEATURES)

    @staticmethod
    def _critic(width):
        return nn.Sequential(nn.Linear(width + 2, width), nn.SiLU(), nn.Linear(width, 1))

    def state(self, obs):
        features, holdings, active, cash = unpack(obs)
        encoded, mask = self.encoder(features, active)
        balances = torch.cat((holdings, cash), 1)
        return encoded, mask, balances

    def sample(self, obs, *, deterministic=False, detach_encoder=False):
        encoded, mask, balances = self.state(obs)
        if detach_encoder:
            encoded = encoded.detach()
        distribution = self.actor(torch.cat((encoded, balances.unsqueeze(-1)), -1))
        mean, log_std = distribution.unbind(-1)
        normal = torch.distributions.Normal(mean, log_std.clamp(-5, 1).exp())
        latent = mean if deterministic else normal.rsample()
        scores = torch.sigmoid(latent)
        # Exact density of independent sigmoid Gaussian scores, NOT simplex weights.
        jacobian = -F.softplus(-latent) - F.softplus(latent)
        log_prob = ((normal.log_prob(latent) - jacobian) * mask).sum(1, keepdim=True)
        return scores * mask, log_prob

    def values(self, obs, scores, *, detach_encoder=False):
        encoded, mask, balances = self.state(obs)
        if detach_encoder:
            encoded = encoded.detach()
        scores = scores * mask
        # Critic sees the same normalized allocation used by the shared broker.
        total = scores.sum(1, keepdim=True)
        cash_only = torch.zeros_like(scores)
        cash_only[:, -1] = 1
        weights = torch.where(total > 0, scores / total.clamp_min(1e-12), cash_only)
        inputs = torch.cat((encoded, balances.unsqueeze(-1), weights.unsqueeze(-1)), -1)
        denominator = mask.sum(1, keepdim=True)
        return tuple(
            (head(inputs).squeeze(-1) * mask).sum(1, keepdim=True) / denominator
            for head in (self.q1, self.q2)
        )

    def reconstruct(self, features, active, hidden, asset_ids):
        if hidden.dtype != torch.bool or (hidden & ~active).any():
            raise ValueError("only active stocks can be reconstruction targets")
        if not hidden.any() or ((active & ~hidden).sum(1) == 0).any():
            raise ValueError("each batch requires visible context and masked targets")
        encoded, visible = self.encoder(features, active & ~hidden)
        # IDs are training-only queries; no hidden target values enter this path.
        queries = self.decoder_queries(asset_ids) + self.mask_token
        decoded, _ = self.decoder_attention(
            queries, encoded, encoded, key_padding_mask=~visible, need_weights=False
        )
        return self.decoder(decoded)

    def reconstruction_loss(self, features, active, hidden, asset_ids):
        prediction = self.reconstruct(features, active, hidden, asset_ids)
        return F.mse_loss(prediction[hidden], features.detach()[hidden])

    def predict(self, observation, deterministic=True):
        self.eval()
        with torch.no_grad():
            values = torch.as_tensor(np.asarray(observation), dtype=torch.float32)
            single = values.ndim == 1
            scores, _ = self.sample(values.unsqueeze(0) if single else values,
                                    deterministic=deterministic)
        result = scores.cpu().numpy()
        return (result[0] if single else result), None


class MaskedSACLearner:
    """Small CPU research SAC with independent reconstruction and RL updates."""

    def __init__(self, network, learning_rate=3e-4, reward_scale=1.0,
                 mae_encoder_learning_rate=None):
        if not math.isfinite(reward_scale) or not 0 < reward_scale <= 1000:
            raise ValueError("reward scale must be finite and within (0,1000]")
        self.reward_scale = float(reward_scale)
        auxiliary_rate = (learning_rate if mae_encoder_learning_rate is None
                          else mae_encoder_learning_rate)
        if not math.isfinite(auxiliary_rate) or not 0 <= auxiliary_rate <= 1:
            raise ValueError("auxiliary encoder learning rate must be finite and within [0,1]")
        self.mae_encoder_learning_rate = float(auxiliary_rate)
        self.network = network
        self.target = copy.deepcopy(network).eval()
        self.target.requires_grad_(False)
        self.critic_parameters = [
            *network.encoder.parameters(), *network.q1.parameters(), *network.q2.parameters()
        ]
        self.critic_optimizer = torch.optim.Adam(self.critic_parameters, lr=learning_rate)
        self.actor_optimizer = torch.optim.Adam(network.actor.parameters(), lr=learning_rate)
        # Keep a zero-lr encoder group so zero_grad also clears its critic gradients.
        # This isolates the auxiliary update; the critic still trains the encoder.
        self.mae_optimizer = torch.optim.Adam([
            {"params": list(network.encoder.parameters()), "lr": self.mae_encoder_learning_rate},
            {"params": [
                network.mask_token, *network.decoder_queries.parameters(),
                *network.decoder_attention.parameters(), *network.decoder.parameters(),
            ], "lr": learning_rate},
        ])
        self.log_alpha = torch.tensor(math.log(0.05), requires_grad=True)
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=learning_rate)
        self.updates = 0

    def probe(self, obs, actions, rewards, next_obs, done, mae_batch, discounts=0.99):
        """Observe gradients without consuming the optimization RNG stream."""
        net = self.network
        encoder = list(net.encoder.parameters())
        actor = list(net.actor.parameters())

        def gradient(loss, parameters):
            gradients = torch.autograd.grad(loss, parameters, retain_graph=True, allow_unused=True)
            return torch.cat([
                (torch.zeros_like(p) if g is None else g).flatten()
                for p, g in zip(parameters, gradients, strict=True)
            ]).detach()

        with torch.random.fork_rng(devices=[]):
            alpha = self.log_alpha.detach().exp()
            with torch.no_grad():
                next_action, next_logp = net.sample(next_obs)
                q1, q2 = self.target.values(next_obs, next_action)
                target = self.reward_scale * rewards + discounts * (1 - done) * (
                    torch.minimum(q1, q2) - alpha * next_logp
                )
            q1, q2 = net.values(obs, actions)
            td_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
            critic_gradient = gradient(td_loss, encoder)
            action, logp = net.sample(obs, detach_encoder=True)
            actor_q1, actor_q2 = net.values(obs, action, detach_encoder=True)
            value_gradient = gradient(-torch.minimum(actor_q1, actor_q2).mean(), actor)
            entropy_gradient = gradient((alpha * logp).mean(), actor)
            result = {
                "rawRewardAbsMean": float(rewards.abs().mean()),
                "scaledRewardAbsMean": float((rewards * self.reward_scale).abs().mean()),
                "entropyTermAbsMean": float((alpha * logp).abs().mean().detach()),
                "actorValueGradientNorm": float(value_gradient.norm()),
                "actorEntropyGradientNorm": float(entropy_gradient.norm()),
                "criticEncoderGradientNorm": float(critic_gradient.norm()),
                "tdErrorAbsMean": float((q1 - target).abs().mean().detach()),
                "activeAssetMean": float(unpack(obs)[2].float().sum(1).mean()),
            }
            if net.variant == "masked_attention":
                mae_gradient = gradient(net.reconstruction_loss(*mae_batch), encoder)
                result["maeEncoderGradientNorm"] = float(mae_gradient.norm())
                result["encoderGradientCosine"] = float(F.cosine_similarity(
                    critic_gradient, mae_gradient, dim=0
                ))
            return result

    def update(self, obs, actions, rewards, next_obs, done, mae_batch, *, diagnose=False,
               discounts=None):
        if discounts is None:
            discounts = 0.99
        elif (discounts.shape != rewards.shape or not torch.isfinite(discounts).all()
              or not ((discounts > 0) & (discounts <= 1)).all()):
            raise ValueError("discounts must match rewards and be finite within (0,1]")
        net = self.network
        net.train()
        diagnostics = (
            self.probe(obs, actions, rewards, next_obs, done, mae_batch, discounts)
            if diagnose else {}
        )
        before = (
            torch.cat([p.detach().flatten() for p in net.encoder.parameters()]).clone()
            if diagnose else None
        )
        alpha = self.log_alpha.detach().exp()
        with torch.no_grad():
            next_action, next_log_prob = net.sample(next_obs)
            q1, q2 = self.target.values(next_obs, next_action)
            target = self.reward_scale * rewards + discounts * (1 - done) * (
                torch.minimum(q1, q2) - alpha * next_log_prob
            )
        q1, q2 = net.values(obs, actions)
        critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic_parameters, 10)
        self.critic_optimizer.step()
        after_critic = (
            torch.cat([p.detach().flatten() for p in net.encoder.parameters()]).clone()
            if diagnose else None
        )

        # Freeze Q heads, but retain dQ/da for the actor. Encoder is detached.
        heads = [*net.q1.parameters(), *net.q2.parameters()]
        for parameter in heads:
            parameter.requires_grad_(False)
        action, log_prob = net.sample(obs, detach_encoder=True)
        q1, q2 = net.values(obs, action, detach_encoder=True)
        actor_loss = (alpha * log_prob - torch.minimum(q1, q2)).mean()
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()
        for parameter in heads:
            parameter.requires_grad_(True)
        # Sigmoid scores are in (0,1): target differential entropy is negative.
        active_count = unpack(obs)[2].sum(1, keepdim=True) + 1
        target_entropy = -0.5 * active_count
        alpha_loss = -(self.log_alpha * (log_prob.detach() + target_entropy)).mean()
        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()
        with torch.no_grad():
            self.log_alpha.clamp_(-10, 2)

        reconstruction_loss = torch.tensor(0.0)
        if net.variant == "masked_attention":
            self.mae_optimizer.zero_grad()
            reconstruction_loss = net.reconstruction_loss(*mae_batch)
            reconstruction_loss.backward()
            nn.utils.clip_grad_norm_(net.encoder.parameters(), 10)
            self.mae_optimizer.step()
        if diagnose:
            after = torch.cat([p.detach().flatten() for p in net.encoder.parameters()])
            critic_step = after_critic - before
            mae_step = after - after_critic
            diagnostics.update({
                "criticEncoderDeltaNorm": float(critic_step.norm()),
                "maeEncoderDeltaNorm": float(mae_step.norm()),
                "encoderStepCosine": float(F.cosine_similarity(critic_step, mae_step, dim=0)),
            })
        with torch.no_grad():
            for current, target_parameter in zip(
                net.parameters(), self.target.parameters(), strict=True
            ):
                target_parameter.lerp_(current, 0.005)
        self.updates += 1
        return {
            "criticLoss": float(critic_loss.detach()),
            "actorLoss": float(actor_loss.detach()),
            "reconstructionLoss": float(reconstruction_loss.detach()),
            "alpha": float(self.log_alpha.detach().exp()),
            **diagnostics,
        }
