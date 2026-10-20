"""Masked deterministic TD3 with twin Q, delayed actor and smoothed target policy."""

import copy
import math

import torch
from torch import nn
from torch.nn import functional as F

from quant_platform.rl.masked_portfolio import MaskedSACNetwork, unpack

ARCHITECTURE = "masked-set-td3-v1"


class MaskedTD3Network(MaskedSACNetwork):
    architecture = ARCHITECTURE

    def __init__(self, training_assets, width=32, variant="masked_attention"):
        super().__init__(training_assets, width, variant)
        self.actor = nn.Sequential(nn.Linear(width + 1, width), nn.SiLU(), nn.Linear(width, 1))

    def sample(self, obs, *, deterministic=False, detach_encoder=False):
        encoded, mask, balances = self.state(obs)
        if detach_encoder:
            encoded = encoded.detach()
        scores = self.actor(torch.cat((encoded, balances.unsqueeze(-1)), -1)).squeeze(-1).sigmoid()
        if not deterministic:
            scores = (scores + torch.randn_like(scores) * 0.1).clamp(0, 1)
        return scores * mask, None


class MaskedTD3Learner:
    def __init__(self, network, learning_rate=3e-4, reward_scale=1.0,
                 mae_encoder_learning_rate=None):
        if not math.isfinite(reward_scale) or not 0 < reward_scale <= 1000:
            raise ValueError("invalid reward scale")
        self.reward_scale = reward_scale
        self.mae_encoder_learning_rate = (
            learning_rate if mae_encoder_learning_rate is None else mae_encoder_learning_rate
        )
        if (not math.isfinite(self.mae_encoder_learning_rate)
                or not 0 <= self.mae_encoder_learning_rate <= 1):
            raise ValueError("invalid auxiliary encoder learning rate")
        self.network = network
        self.target = copy.deepcopy(network).eval()
        self.target.requires_grad_(False)
        self.critic_parameters = [
            *network.encoder.parameters(), *network.q1.parameters(), *network.q2.parameters()
        ]
        self.critic_optimizer = torch.optim.Adam(self.critic_parameters, lr=learning_rate)
        self.actor_optimizer = torch.optim.Adam(network.actor.parameters(), lr=learning_rate)
        self.mae_optimizer = torch.optim.Adam([
            {"params": list(network.encoder.parameters()), "lr": self.mae_encoder_learning_rate},
            {"params": [
                network.mask_token, *network.decoder_queries.parameters(),
                *network.decoder_attention.parameters(), *network.decoder.parameters(),
            ], "lr": learning_rate},
        ])
        self.updates = self.actor_updates = 0

    def target_actions(self, obs):
        with torch.no_grad():
            scores, _ = self.target.sample(obs, deterministic=True)
            mask = torch.cat((unpack(obs)[2], torch.ones_like(obs[:, :1], dtype=torch.bool)), 1)
            noise = (torch.randn_like(scores) * 0.2).clamp(-0.5, 0.5)
            return (scores + noise).clamp(0, 1) * mask

    def update(self, obs, actions, rewards, next_obs, done, mae_batch, *, diagnose=False,
               discounts=None):
        if discounts is None:
            discounts = 0.99
        elif (discounts.shape != rewards.shape or not torch.isfinite(discounts).all()
              or not ((discounts > 0) & (discounts <= 1)).all()):
            raise ValueError("discounts must match rewards and be finite within (0,1]")
        if diagnose:
            raise ValueError("SAC entropy diagnostics do not apply to TD3")
        net = self.network
        with torch.no_grad():
            next_action = self.target_actions(next_obs)
            q1, q2 = self.target.values(next_obs, next_action)
            target = self.reward_scale * rewards + discounts * (1 - done) * torch.minimum(q1, q2)
        q1, q2 = net.values(obs, actions)
        critic_loss = F.mse_loss(q1, target) + F.mse_loss(q2, target)
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        nn.utils.clip_grad_norm_(self.critic_parameters, 10)
        self.critic_optimizer.step()
        self.updates += 1
        actor_loss = torch.tensor(0.0)
        if self.updates % 2 == 0:
            heads = [*net.q1.parameters(), *net.q2.parameters()]
            for parameter in heads:
                parameter.requires_grad_(False)
            scores, _ = net.sample(obs, deterministic=True, detach_encoder=True)
            actor_loss = -net.values(obs, scores, detach_encoder=True)[0].mean()
            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()
            for parameter in heads:
                parameter.requires_grad_(True)
            self.actor_updates += 1
        self.mae_optimizer.zero_grad()
        reconstruction = net.reconstruction_loss(*mae_batch)
        reconstruction.backward()
        nn.utils.clip_grad_norm_(net.encoder.parameters(), 10)
        self.mae_optimizer.step()
        if self.updates % 2 == 0:
            with torch.no_grad():
                for source, target_parameter in zip(
                    net.parameters(), self.target.parameters(), strict=True
                ):
                    target_parameter.lerp_(source, 0.005)
        return {
            "criticLoss": critic_loss.item(), "actorLoss": actor_loss.item(),
            "reconstructionLoss": reconstruction.item(), "actorUpdates": self.actor_updates,
        }
