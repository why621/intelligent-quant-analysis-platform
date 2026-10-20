"""Bounded local research training; no production registry or network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from quant_platform.models import TradingCosts
from quant_platform.rl.changing_pool import ChangingPoolEpisode
from quant_platform.rl.features import MIN_WARMUP
from quant_platform.rl.masked_portfolio import ARCHITECTURE, MaskedSACLearner, MaskedSACNetwork
from quant_platform.rl.portfolio_env import PortfolioEpisode
from quant_platform.rl.portfolio_features import MAX_ASSETS, prepare_panel
from quant_platform.rl.portfolio_policy import costs_metadata
from quant_platform.rl.portfolio_train import training_frames


def sample_reconstruction(panel, rng, batch_size=16):
    count = min(MAX_ASSETS, len(panel.symbols))
    ids = np.stack([rng.choice(len(panel.symbols), count, replace=False)
                    for _ in range(batch_size)])
    bars = rng.integers(MIN_WARMUP, len(panel.dates), size=batch_size)
    features = panel.features[bars[:, None], ids].astype(np.float32)
    hidden = np.zeros((batch_size, count), dtype=bool)
    for row in hidden:
        # Variable masks with at least one visible asset and one masked target.
        row[rng.choice(count, int(rng.integers(1, count)), replace=False)] = True
    return (
        torch.tensor(features), torch.ones_like(torch.tensor(hidden)),
        torch.tensor(hidden), torch.tensor(ids),
    )


def save_research(network, destination, metadata):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    weights = destination / "research.pt"
    torch.save(network.state_dict(), weights)
    metadata = {
        **metadata, "architecture": getattr(network, "architecture", ARCHITECTURE),
        "purpose": "local_smoke_only",
        "releaseEligible": False, "trainingAssets": network.training_assets,
        "variant": network.variant,
        "width": network.width, "weightsSha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
    }
    (destination / "research.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def load_research(destination):
    destination = Path(destination)
    metadata = json.loads((destination / "research.json").read_text(encoding="utf-8"))
    weights = destination / "research.pt"
    classes = {ARCHITECTURE: MaskedSACNetwork}
    from quant_platform.rl.masked_ppo import ARCHITECTURE as PPO_ARCHITECTURE
    from quant_platform.rl.masked_ppo import MaskedPPONetwork

    classes[PPO_ARCHITECTURE] = MaskedPPONetwork
    from quant_platform.rl.masked_td3 import ARCHITECTURE as TD3_ARCHITECTURE
    from quant_platform.rl.masked_td3 import MaskedTD3Network

    classes[TD3_ARCHITECTURE] = MaskedTD3Network
    if (metadata["architecture"] not in classes
            or metadata["purpose"] != "local_smoke_only" or metadata["releaseEligible"] is not False
            or hashlib.sha256(weights.read_bytes()).hexdigest() != metadata["weightsSha256"]):
        raise ValueError("invalid or corrupted local research bundle")
    network = classes[metadata["architecture"]](
        metadata["trainingAssets"], metadata["width"],
        variant=metadata.get("variant", "masked_attention"),
    )
    network.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    network.eval()
    return network, metadata


def train_masked(
    frames, *, asset_types, splits, destination, steps=256, max_seconds=180,
    seed=42, episode_bars=16, costs=None, variant="masked_attention",
    reward_scale=1.0, diagnostic_interval=0, checkpoints=(), mae_encoder_learning_rate=None,
    pool_switch_interval=0,
    formal_candidate=False,
    algorithm="masked_sac",
):
    if algorithm not in ("masked_sac", "masked_td3"):
        raise ValueError("this replay trainer accepts only SAC or TD3")
    if algorithm == "masked_td3" and (diagnostic_interval or variant != "masked_attention"):
        raise ValueError("TD3 requires masked attention and no SAC entropy diagnostics")
    lower, upper = (65536, 65536) if formal_candidate else (64, 10000)
    if isinstance(steps, bool) or not isinstance(steps, int) or not lower <= steps <= upper:
        raise ValueError(f"steps must be {lower}..{upper}")
    if not np.isfinite(max_seconds) or not 1 <= max_seconds <= (3600 if formal_candidate else 600):
        raise ValueError("wall-clock budget exceeds the permitted candidate scope")
    if Path(destination).exists():
        raise ValueError("research destination exists; use a new run")
    if (isinstance(pool_switch_interval, bool) or not isinstance(pool_switch_interval, int)
            or pool_switch_interval < 0):
        raise ValueError("pool switch interval must be a nonnegative integer")
    if (isinstance(diagnostic_interval, bool) or not isinstance(diagnostic_interval, int)
            or diagnostic_interval < 0):
        raise ValueError("diagnostic interval must be a nonnegative integer")
    if len(set(checkpoints)) != len(checkpoints) or any(
        isinstance(step, bool) or not isinstance(step, int) or not 32 <= step < steps
        for step in checkpoints
    ):
        raise ValueError("checkpoints must be distinct steps in [32, requested steps)")
    checkpoint_paths = {
        step: Path(destination).with_name(f"{Path(destination).name}-step-{step}")
        for step in checkpoints
    }
    if any(path.exists() for path in checkpoint_paths.values()):
        raise ValueError("checkpoint destination exists")
    costs = costs or TradingCosts()
    # Both RL and MAE receive only this chronological training slice.
    panel = prepare_panel(training_frames(frames, splits))
    episode_class = ChangingPoolEpisode if pool_switch_interval else PortfolioEpisode
    episode = episode_class(
        panel, asset_types=asset_types, trading_costs=costs, episode_bars=episode_bars
    )
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    switch_rng = np.random.default_rng(seed + 20000)
    network_class, learner_class = MaskedSACNetwork, MaskedSACLearner
    if algorithm == "masked_td3":
        from quant_platform.rl.masked_td3 import MaskedTD3Learner, MaskedTD3Network

        network_class, learner_class = MaskedTD3Network, MaskedTD3Learner
    network = network_class(len(panel.symbols), variant=variant)
    learner = learner_class(
        network, reward_scale=reward_scale, mae_encoder_learning_rate=mae_encoder_learning_rate
    )
    # Architecture initialization must not change subsequent action noise.
    torch.manual_seed(seed + 10000)
    observation, _ = episode.reset(seed=seed)
    memory = []
    losses = []
    diagnostics = []
    started = time.monotonic()
    completed = 0
    market_steps = 0
    episode_decisions = 0
    pending_pool = None
    pool_events = []
    pool_event_count = 0
    for step in range(steps):
        if time.monotonic() - started >= max_seconds:
            break
        action = (rng.uniform(0, 1, MAX_ASSETS + 1).astype(np.float32) if step < 32
                  else network.predict(observation, deterministic=False)[0])
        next_observation, reward, done, _, _ = episode.step(action)
        market_steps += 1
        episode_decisions += 1
        discount = 0.99
        if pool_switch_interval and not done:
            if pending_pool is None and episode_decisions % pool_switch_interval == 0:
                count = int(switch_rng.integers(episode.min_assets, episode.max_assets + 1))
                pending_pool = tuple(
                    switch_rng.choice(panel.symbols, count, replace=False).tolist()
                )
            if pending_pool is not None:
                next_observation, switch_reward, done, _, event = episode.switch_pool(pending_pool)
                reward, discount = combine_pool_transition(reward, switch_reward)
                market_steps += 1
                pool_event_count += 1
                if len(pool_events) < 256:
                    pool_events.append({
                        "policyStep": step + 1, "date": event["date"],
                        **event["poolTransition"],
                    })
                if not event["poolTransition"]["retryRequired"]:
                    pending_pool = None
        memory.append((observation, action, [reward], next_observation, [float(done)], [discount]))
        observation = next_observation
        if done:
            observation, _ = episode.reset()
            episode_decisions = 0
            pending_pool = None
        if len(memory) >= 32:
            batch = [memory[index] for index in rng.integers(len(memory), size=32)]
            tensors = [torch.tensor(np.asarray(items), dtype=torch.float32)
                       for items in zip(*batch, strict=True)]
            diagnose = diagnostic_interval > 0 and (step + 1) % diagnostic_interval == 0
            losses.append(learner.update(
                *tensors[:5], sample_reconstruction(panel, rng), diagnose=diagnose,
                discounts=tensors[5] if pool_switch_interval else None,
            ))
            if diagnose:
                diagnostics.append({"step": step + 1, **losses[-1]})
        completed = step + 1
        if completed in checkpoint_paths:
            save_research(network, checkpoint_paths[completed], {
                "variant": variant, "actualSteps": completed, "rewardScale": reward_scale,
                "maeEncoderLearningRate": learner.mae_encoder_learning_rate,
                "poolSwitchInterval": pool_switch_interval, "marketSteps": market_steps,
                "seed": seed, "splits": dict(splits), "trainingUniverse": list(panel.symbols),
                "dataHashes": dict(panel.data_hashes), "optimizerUpdates": learner.updates,
                "checkpointKind": "intermediate_validation_only", "performanceStatus": "unproven",
            })
    if not learner.updates or not all(np.isfinite(list(item.values())).all() for item in losses):
        raise RuntimeError("no finite optimizer evidence; refusing to save")
    metadata = {
        "algorithm": algorithm,
        "seed": seed, "requestedSteps": steps, "actualSteps": completed,
        "formalCandidateRun": formal_candidate, "maxSeconds": max_seconds,
        "variant": variant,
        "rewardScale": reward_scale, "diagnostics": diagnostics,
        "maeEncoderLearningRate": learner.mae_encoder_learning_rate,
        "poolSwitchInterval": pool_switch_interval, "marketSteps": market_steps,
        "poolEventCount": pool_event_count, "poolEvents": pool_events,
        "stepBudgetUnit": "policy_decisions",
        "checkpointSteps": [step for step in checkpoints if step <= completed],
        "parameterCount": sum(p.numel() for p in network.parameters()),
        "optimizerUpdates": learner.updates, "elapsedSeconds": time.monotonic() - started,
        "stopReason": "step_budget" if completed == steps else "time_budget",
        "splits": dict(splits), "trainingUniverse": list(panel.symbols),
        "dataHashes": dict(panel.data_hashes), "costs": costs_metadata(costs),
        "sampling": episode.sample_log, "lossesFirst": losses[0], "lossesLast": losses[-1],
        "reconstruction": ("masked_causal_features_training_only_id_queries"
                           if variant == "masked_attention" else "disabled_ablation"),
        "actionDensity": ("deterministic_scores_with_exploration_noise" if algorithm == "masked_td3"
                          else "sigmoid_gaussian_scores_not_simplex"),
        **({"actorUpdates": learner.actor_updates, "policyDelay": 2,
            "targetNoiseStd": 0.2, "targetNoiseClip": 0.5}
           if algorithm == "masked_td3" else {}),
        "poolChanges": ("in_episode_exogenous_transition" if pool_switch_interval
                        else "episode_reset_only"),
        "performanceStatus": "unproven",
        "validationExecuted": False, "testExecuted": False,
    }
    save_research(network, destination, metadata)
    restored, _ = load_research(destination)
    np.testing.assert_allclose(
        network.predict(observation)[0], restored.predict(observation)[0], rtol=0, atol=0
    )
    (Path(destination) / "save-load.json").write_text(
        '{"deterministicOutputIdentical": true}\n', encoding="utf-8"
    )
    return restored, metadata


def combine_pool_transition(policy_reward, switch_reward):
    """Two market sessions, one policy decision; no fabricated switch action."""
    return policy_reward + 0.99 * switch_reward, 0.99 ** 2


def evaluate_research(network, frames, *, asset_types, costs, start, end, in_sample_end):
    """Read-only OOS replay, using the exact shared-account execution engine."""
    if (pd.Timestamp(start) <= pd.Timestamp(in_sample_end)
            or pd.Timestamp(end) < pd.Timestamp(start)):
        raise ValueError("evaluation must be strictly out of sample")
    selected = {
        symbol: frame.loc[pd.to_datetime(frame["date"]) <= pd.Timestamp(end)].copy()
        for symbol, frame in frames.items()
    }
    panel = prepare_panel(selected)
    requested = pd.Timestamp(start)
    position = int(panel.dates.searchsorted(requested))
    if position >= len(panel.dates) or panel.dates[position] != requested:
        raise ValueError("evaluation start must be an actual common session")
    if panel.dates[-1] != pd.Timestamp(end):
        raise ValueError("evaluation end must be an actual common session")
    episode = PortfolioEpisode(
        panel, asset_types=asset_types, trading_costs=costs, random_subsets=False,
        random_start=False, episode_bars=len(panel.dates) - position - 1,
    )
    observation, _ = episode.reset(options={"start_index": position})
    curve = [episode.account()]
    gross_traded = 0.0
    for _ in range(episode.episode_bars):
        action, _ = network.predict(observation)
        observation, _, _, _, info = episode.step(action)
        gross_traded += sum(abs(fill["quantity"] * fill["price"]) for fill in info["fills"])
        curve.append({key: value for key, value in info.items() if key != "fills"})
    equities = np.array([row["equity"] for row in curve])
    return {
        "evidenceKind": "local_research_replay_not_release_or_alpha_proof",
        "symbols": list(panel.symbols), "start": start, "end": end,
        "totalReturnPct": (curve[-1]["equity"] / curve[0]["equity"] - 1) * 100,
        "maxDrawdownPct": float((1 - equities / np.maximum.accumulate(equities)).max() * 100),
        "grossTurnoverInitialCapital": gross_traded / curve[0]["equity"],
        "cumulativeFees": curve[-1]["cumulativeFees"],
        "cumulativeSlippage": curve[-1]["cumulativeSlippage"],
        "tradeCount": curve[-1]["tradeCount"],
        "curve": curve,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--asset-types", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=256)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--pool-switch-interval", type=int, default=0)
    args = parser.parse_args()
    symbols = args.symbols.split(",")
    if len(set(symbols)) != len(symbols) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", symbol) for symbol in symbols
    ):
        parser.error("symbols must be distinct simple identifiers")
    frames = {symbol: pd.read_csv(args.data_dir / f"{symbol}.csv") for symbol in symbols}
    _, metadata = train_masked(
        frames, asset_types=json.loads(args.asset_types.read_text(encoding="utf-8")),
        splits=json.loads(args.splits.read_text(encoding="utf-8")),
        destination=args.destination, steps=args.steps, max_seconds=args.max_seconds,
        pool_switch_interval=args.pool_switch_interval,
    )
    print(json.dumps({key: metadata[key] for key in
                      ("actualSteps", "optimizerUpdates", "elapsedSeconds", "stopReason")}))


if __name__ == "__main__":
    main()
