"""On-policy masked-attention PPO; shared representation, distinct PPO objective."""

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from quant_platform.rl.masked_portfolio import MaskedSACNetwork

ARCHITECTURE = "masked-set-ppo-v1"


class MaskedPPONetwork(MaskedSACNetwork):
    architecture = ARCHITECTURE

    def __init__(self, training_assets, width=32, variant="masked_attention"):
        super().__init__(training_assets, width, variant)
        del self.q1, self.q2
        self.value_head = nn.Sequential(
            nn.Linear(width + 1, width), nn.SiLU(), nn.Linear(width, 1)
        )

    def distribution_value(self, obs):
        encoded, mask, balances = self.state(obs)
        inputs = torch.cat((encoded, balances.unsqueeze(-1)), -1)
        mean, log_std = self.actor(inputs).unbind(-1)
        distribution = torch.distributions.Normal(mean, log_std.clamp(-5, 1).exp())
        value = (self.value_head(inputs).squeeze(-1) * mask).sum(1) / mask.sum(1)
        return distribution, value, mask

    def policy_terms(self, obs, latent):
        distribution, value, mask = self.distribution_value(obs)
        jacobian = -F.softplus(-latent) - F.softplus(latent)
        log_prob = ((distribution.log_prob(latent) - jacobian) * mask).sum(1)
        return log_prob, value

    def act(self, observation):
        with torch.no_grad():
            obs = torch.as_tensor(np.asarray(observation), dtype=torch.float32)[None]
            distribution, value, mask = self.distribution_value(obs)
            latent = distribution.sample()
            log_prob, _ = self.policy_terms(obs, latent)
            scores = latent.sigmoid() * mask
        return scores[0].numpy(), latent[0].numpy(), log_prob.item(), value.item()


def generalized_advantages(rewards, values, next_values, dones, discounts, durations,
                           lam=0.95):
    """Each decision may span two sessions; terminal resets never leak into GAE."""
    arrays = [np.asarray(x, dtype=np.float64) for x in
              (rewards, values, next_values, dones, discounts, durations)]
    r, v, nv, done, gamma, elapsed = arrays
    if (not all(x.ndim == 1 and x.shape == r.shape and np.isfinite(x).all() for x in arrays)
            or not np.isin(done, [0, 1]).all()
            or not ((gamma > 0) & (gamma <= 1)).all()
            or not np.isin(elapsed, [1, 2]).all()):
        raise ValueError("invalid chronological rollout")
    advantages = np.zeros_like(r)
    carry = 0.0
    for i in reversed(range(len(r))):
        delta = r[i] + gamma[i] * (1 - done[i]) * nv[i] - v[i]
        carry = delta + gamma[i] * lam ** elapsed[i] * (1 - done[i]) * carry
        advantages[i] = carry
    return advantages.astype(np.float32), (advantages + v).astype(np.float32)


class MaskedPPOLearner:
    def __init__(self, network, learning_rate=3e-4, mae_encoder_learning_rate=3e-5):
        self.network = network
        self.mae_encoder_learning_rate = mae_encoder_learning_rate
        self.parameters = [
            *network.encoder.parameters(), *network.actor.parameters(),
            *network.value_head.parameters(),
        ]
        self.optimizer = torch.optim.Adam(self.parameters, lr=learning_rate)
        self.mae_optimizer = torch.optim.Adam([
            {"params": list(network.encoder.parameters()), "lr": mae_encoder_learning_rate},
            {"params": [
                network.mask_token, *network.decoder_queries.parameters(),
                *network.decoder_attention.parameters(), *network.decoder.parameters(),
            ], "lr": learning_rate},
        ])
        self.updates = 0

    def update(self, rollout, mae_batch, epochs=4, batch_size=32):
        # Rollout is consumed once; callers must clear it before collecting new data.
        obs, latent, old_logp, advantages, returns = [
            torch.as_tensor(x, dtype=torch.float32).detach() for x in rollout
        ]
        advantages = (advantages - advantages.mean()) / advantages.std(
            unbiased=False
        ).clamp_min(1e-8)
        totals = []
        for _ in range(epochs):
            order = torch.randperm(len(obs))
            for indices in order.split(batch_size):
                logp, value = self.network.policy_terms(obs[indices], latent[indices])
                ratio = (logp - old_logp[indices]).exp()
                policy_loss = -torch.minimum(
                    ratio * advantages[indices],
                    ratio.clamp(0.8, 1.2) * advantages[indices],
                ).mean()
                value_loss = F.mse_loss(value, returns[indices])
                loss = policy_loss + 0.5 * value_loss
                if not torch.isfinite(loss):
                    raise RuntimeError("nonfinite PPO objective")
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.parameters, 0.5)
                self.optimizer.step()
                self.updates += 1
                totals.append((policy_loss.item(), value_loss.item()))
        # Auxiliary update follows all PPO epochs, never changes a collection policy mid-rollout.
        self.mae_optimizer.zero_grad()
        reconstruction = self.network.reconstruction_loss(*mae_batch)
        reconstruction.backward()
        nn.utils.clip_grad_norm_(self.network.encoder.parameters(), 10)
        self.mae_optimizer.step()
        return {
            "actorLoss": float(np.mean([x[0] for x in totals])),
            "valueLoss": float(np.mean([x[1] for x in totals])),
            "reconstructionLoss": reconstruction.item(),
        }
