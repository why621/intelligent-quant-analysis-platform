"""Bounded PPO training on the shared account; no replay buffer or SAC updates."""

import time
from pathlib import Path

import numpy as np
import torch

from quant_platform.models import TradingCosts
from quant_platform.rl.changing_pool import ChangingPoolEpisode
from quant_platform.rl.masked_ppo import (
    MaskedPPOLearner,
    MaskedPPONetwork,
    generalized_advantages,
)
from quant_platform.rl.masked_train import (
    combine_pool_transition,
    load_research,
    sample_reconstruction,
    save_research,
)
from quant_platform.rl.portfolio_features import prepare_panel
from quant_platform.rl.portfolio_policy import costs_metadata
from quant_platform.rl.portfolio_train import training_frames


def train_masked_ppo(
    frames, *, asset_types, splits, destination, steps=256, max_seconds=180, seed=42,
    episode_bars=16, costs=None, pool_switch_interval=4, formal_candidate=False,
    mae_encoder_learning_rate=3e-5,
):
    if (isinstance(steps, bool) or not isinstance(steps, int)
            or not ((steps == 65536) if formal_candidate else (64 <= steps <= 10000))):
        raise ValueError("invalid PPO step budget")
    if (not np.isfinite(max_seconds)
            or not 1 <= max_seconds <= (3600 if formal_candidate else 600)):
        raise ValueError("invalid PPO wall-clock budget")
    if (isinstance(pool_switch_interval, bool) or not isinstance(pool_switch_interval, int)
            or pool_switch_interval < 0 or Path(destination).exists()):
        raise ValueError("invalid switching interval or existing destination")
    panel = prepare_panel(training_frames(frames, splits))
    costs = costs or TradingCosts()
    episode = ChangingPoolEpisode(
        panel, asset_types=asset_types, trading_costs=costs, episode_bars=episode_bars
    )
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    network = MaskedPPONetwork(len(panel.symbols))
    learner = MaskedPPOLearner(network, mae_encoder_learning_rate=mae_encoder_learning_rate)
    torch.manual_seed(seed + 10000)
    rng, switch_rng = np.random.default_rng(seed), np.random.default_rng(seed + 20000)
    observation, _ = episode.reset(seed=seed)
    started = time.monotonic()
    rollout, losses, events = [], [], []
    completed = market_steps = decisions = event_count = 0
    pending = None

    def optimize():
        arrays = [np.asarray(items) for items in zip(*rollout, strict=True)]
        obs, latents, logp, values, rewards, next_values, dones, discounts, durations = arrays
        advantages, returns = generalized_advantages(
            rewards, values, next_values, dones, discounts, durations
        )
        losses.append(learner.update(
            (obs, latents, logp, advantages, returns), sample_reconstruction(panel, rng)
        ))
        rollout.clear()

    for step in range(steps):
        if time.monotonic() - started >= max_seconds:
            break
        action, latent, logp, value = network.act(observation)
        next_obs, reward, done, _, _ = episode.step(action)
        market_steps += 1
        decisions += 1
        discount, duration = 0.99, 1
        if pool_switch_interval and not done:
            if pending is None and decisions % pool_switch_interval == 0:
                count = int(switch_rng.integers(episode.min_assets, episode.max_assets + 1))
                pending = tuple(switch_rng.choice(panel.symbols, count, replace=False).tolist())
            if pending is not None:
                next_obs, extra, done, _, event = episode.switch_pool(pending)
                reward, discount = combine_pool_transition(reward, extra)
                duration = 2
                market_steps += 1
                event_count += 1
                if len(events) < 256:
                    events.append({"policyStep": step + 1, **event["poolTransition"]})
                if not event["poolTransition"]["retryRequired"]:
                    pending = None
        with torch.no_grad():
            next_value = network.distribution_value(torch.tensor(next_obs)[None])[1].item()
        rollout.append((
            observation, latent, logp, value, reward, next_value,
            float(done), discount, duration,
        ))
        observation = next_obs
        if done:
            observation, _ = episode.reset()
            decisions, pending = 0, None
        completed = step + 1
        if len(rollout) == 128:
            optimize()
    if rollout:
        optimize()
    if not losses or not all(np.isfinite(list(x.values())).all() for x in losses):
        raise RuntimeError("no finite PPO optimizer evidence")
    metadata = {
        "algorithm": "masked_ppo", "seed": seed, "requestedSteps": steps,
        "actualSteps": completed, "formalCandidateRun": formal_candidate,
        "optimizerUpdates": learner.updates, "maxSeconds": max_seconds,
        "elapsedSeconds": time.monotonic() - started,
        "stopReason": "step_budget" if completed == steps else "time_budget",
        "poolSwitchInterval": pool_switch_interval, "marketSteps": market_steps,
        "poolEventCount": event_count, "poolEvents": events,
        "stepBudgetUnit": "policy_decisions", "splits": dict(splits),
        "trainingUniverse": list(panel.symbols), "dataHashes": dict(panel.data_hashes),
        "costs": costs_metadata(costs), "sampling": episode.sample_log,
        "lossesFirst": losses[0], "lossesLast": losses[-1],
        "rolloutLength": 128, "epochs": 4, "minibatchSize": 32,
        "clipRange": 0.2, "gaeLambda": 0.95,
        "replayBuffer": False, "rewardScale": 1,
        "maeEncoderLearningRate": mae_encoder_learning_rate,
        "actionDensity": "sigmoid_gaussian_scores_not_simplex",
        "poolChanges": ("in_episode_exogenous_transition" if pool_switch_interval
                        else "episode_reset_only"),
        "performanceStatus": "unproven", "validationExecuted": False, "testExecuted": False,
    }
    save_research(network, destination, metadata)
    restored, _ = load_research(destination)
    np.testing.assert_allclose(
        network.predict(observation)[0], restored.predict(observation)[0], atol=0, rtol=0
    )
    return restored, metadata
