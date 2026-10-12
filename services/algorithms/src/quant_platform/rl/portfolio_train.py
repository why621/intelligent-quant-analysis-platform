"""Bounded local joint-portfolio smoke training; no downloads or deployment.

Inputs are explicitly supplied local, immutable daily frames. Calendar splits
are applied BEFORE random episode/pool sampling. Smoke training proves plumbing,
not excess returns, model selection, EarnMore reproduction or deployment fitness.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import PORTFOLIO_EXECUTION_VERSION
from quant_platform.rl.portfolio_env import make_portfolio_env
from quant_platform.rl.portfolio_features import (
    ACTION_SIZE,
    ENVIRONMENT_VERSION,
    MAX_ASSETS,
    OBSERVATION_SIZE,
    observation_signature,
    prepare_panel,
)
from quant_platform.rl.portfolio_policy import (
    PORTFOLIO_ALGORITHMS,
    costs_metadata,
    load_portfolio_bundle,
    save_portfolio_bundle,
    validate_manifest,
    validate_splits,
)


def training_frames(frames: Mapping[str, pd.DataFrame], splits: Mapping) -> dict[str, pd.DataFrame]:
    boundaries = validate_splits(splits)
    start, end = (
        pd.Timestamp(boundaries["trainStartDate"]),
        pd.Timestamp(boundaries["trainEndDate"]),
    )
    selected = {}
    for symbol, frame in frames.items():
        dates = pd.to_datetime(frame["date"], errors="raise")
        selected[symbol] = (
            frame.loc[(dates >= start) & (dates <= end)].copy().reset_index(drop=True)
        )
    return selected


def train_portfolio(
    frames: Mapping[str, pd.DataFrame],
    *,
    asset_types: Mapping[str, str],
    trading_costs: TradingCosts,
    splits: Mapping,
    output_root: Path,
    run_id: str,
    algo: str = "ppo",
    total_timesteps: int = 2_048,
    max_seconds: float = 180.0,
    episode_bars: int = 64,
    seed: int = 42,
    initial_capital: float = 100_000.0,
    band_pct: float = 0.0,
    min_trade_cny: float = 0.0,
    formal_candidate: bool = False,
) -> Path:
    if algo not in PORTFOLIO_ALGORITHMS:
        raise ValueError("joint smoke training supports PPO/SAC/TD3, not DQN")
    if (
        not isinstance(total_timesteps, int)
        or isinstance(total_timesteps, bool)
        or not 64 <= total_timesteps <= (250_000 if formal_candidate else 10_000)
    ):
        raise ValueError("local smoke training is bounded to 64..10000 requested steps")
    if not 1 <= max_seconds <= (3600 if formal_candidate else 600):
        raise ValueError("local smoke wall-clock budget must be within 1..600 seconds")
    boundaries = validate_splits(splits)
    panel = prepare_panel(training_frames(frames, boundaries))
    metadata = {
        "schemaVersion": 1,
        "runId": run_id,
        "algo": algo,
        "portfolioMode": "joint_portfolio",
        "environmentVersion": ENVIRONMENT_VERSION,
        "executionVersion": PORTFOLIO_EXECUTION_VERSION,
        "observationSignature": observation_signature(),
        "observationShape": [OBSERVATION_SIZE],
        "actionShape": [ACTION_SIZE],
        "minAssets": 2,
        "maxAssets": MAX_ASSETS,
        "trainingUniverse": list(panel.symbols),
        "assetTypes": {symbol: asset_types.get(symbol) for symbol in panel.symbols},
        "dataHashes": dict(panel.data_hashes),
        "dataHashScope": "training_split_consumed_daily_OHLC",
        "splits": boundaries,
        "actualTrainingStartDate": panel.dates[0].date().isoformat(),
        "actualTrainingEndDate": panel.dates[-1].date().isoformat(),
        "tradingCosts": costs_metadata(trading_costs),
        "rebalanceBandPct": band_pct,
        "minTradeCny": min_trade_cny,
        "rewardMode": "net_portfolio_log_return",
        "generalization": "unverified",
        "performanceStatus": "unproven",
        "releaseEligible": False,
        "purpose": "formal_candidate" if formal_candidate else "local_smoke_only",
        "weightSelection": "validation_pending" if formal_candidate else "final_smoke_checkpoint",
        "validationExecuted": False,
        "testExecuted": False,
        "seed": seed,
        "requestedTimesteps": total_timesteps,
        "maxSeconds": max_seconds,
        "initialCapital": initial_capital,
        "sampling": {
            "minAssets": 2,
            "maxAssets": min(MAX_ASSETS, len(panel.symbols)),
            "randomAssetSubset": True,
            "randomSlotOrder": True,
            "randomTrainingWindow": True,
            "episodeBars": episode_bars,
            "poolChanges": "episode_reset_only",
            "permutationEquivariant": False,
        },
    }
    validate_manifest(metadata)
    if (Path(output_root) / run_id).exists():
        raise ValueError("portfolio run already exists; use a new run id")
    # Validate episode constraints before importing the optional heavy stack.
    from quant_platform.rl.portfolio_env import PortfolioEpisode

    environment_args = {
        "asset_types": asset_types,
        "trading_costs": trading_costs,
        "initial_capital": initial_capital,
        "episode_bars": episode_bars,
        "band_pct": band_pct,
        "min_trade_cny": min_trade_cny,
    }
    PortfolioEpisode(panel, **environment_args)
    try:
        import torch
        from stable_baselines3 import PPO, SAC, TD3
        from stable_baselines3.common.callbacks import BaseCallback
    except ImportError as exc:
        from quant_platform.rl.errors import RLDependenciesMissing

        raise RLDependenciesMissing(
            "joint smoke training requires optional [rl] dependencies"
        ) from exc

    torch.set_num_threads(1)
    torch.manual_seed(seed)
    environment = make_portfolio_env(panel, **environment_args)
    started = time.monotonic()

    class BoundedRun(BaseCallback):
        stopped_for_time = False

        def _on_step(self):
            if time.monotonic() - started >= max_seconds:
                self.stopped_for_time = True
                return False
            return True

    callback = BoundedRun()
    common = {"seed": seed, "verbose": 0, "device": "cpu", "policy_kwargs": {"net_arch": [64, 64]}}
    if algo == "ppo":
        model = PPO("MlpPolicy", environment, n_steps=128, batch_size=32, n_epochs=3, **common)
    else:
        cls = {"sac": SAC, "td3": TD3}[algo]
        model = cls(
            "MlpPolicy",
            environment,
            learning_starts=32,
            buffer_size=10_000,
            batch_size=32,
            train_freq=4,
            gradient_steps=1,
            **common,
        )
    try:
        model.learn(total_timesteps=total_timesteps, callback=callback)
        metadata.update(
            {
                "actualTimesteps": int(model.num_timesteps),
                "optimizerUpdates": int(model._n_updates),
                "elapsedSeconds": time.monotonic() - started,
                "stopReason": "time_budget" if callback.stopped_for_time else "step_budget",
                "sampledEpisodeCount": environment.episode.episode_count,
                "sampledEpisodes": environment.episode.sample_log,
                "runtime": {"torch": torch.__version__, "device": "cpu", "threads": 1},
            }
        )
        if metadata["actualTimesteps"] <= 0 or metadata["optimizerUpdates"] <= 0:
            raise RuntimeError("budget ended before any optimizer update; no trained bundle saved")
        destination = save_portfolio_bundle(model, output_root, metadata)
        # Real save/load/predict, not a fake environment/model or random-action surrogate.
        restored = load_portfolio_bundle(destination)
        obs, _ = environment.reset(seed=seed)
        action, _ = restored.model.predict(obs, deterministic=True)
        _, reward, _, _, info = environment.step(action)
        (destination / "smoke-verification.json").write_text(
            json.dumps(
                {
                    "loaded": True,
                    "jointActionDimension": len(action),
                    "simultaneousAssets": info["symbols"],
                    "finiteReward": bool(torch.isfinite(torch.tensor(reward)).item()),
                    "equity": info["equity"],
                    "evidenceKind": "local_smoke_not_performance_validation",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return destination
    finally:
        environment.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="local SYMBOL.csv directory")
    parser.add_argument("--symbols", required=True, help="explicit comma-separated training pool")
    parser.add_argument(
        "--asset-types-json",
        type=Path,
        required=True,
        help='JSON mapping, e.g. {"510300":"etf","510050":"etf"}',
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--algo", choices=PORTFOLIO_ALGORITHMS, default="ppo")
    for prefix in ("train", "val", "test"):
        parser.add_argument(
            f"--{prefix}-start", type=date.fromisoformat, required=prefix == "train"
        )
        parser.add_argument(f"--{prefix}-end", type=date.fromisoformat, required=prefix == "train")
    parser.add_argument("--steps", type=int, default=2_048)
    parser.add_argument("--max-seconds", type=float, default=180.0)
    parser.add_argument("--episode-bars", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--commission-pct", type=float, default=0.03)
    parser.add_argument("--stamp-duty-pct", type=float, default=0.05)
    parser.add_argument("--slippage-pct", type=float, default=0.02)
    parser.add_argument("--stamp-duty-mode", choices=("fixed", "asset_date"), default="asset_date")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",")]
    if len(set(symbols)) != len(symbols) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", symbol) for symbol in symbols
    ):
        parser.error("symbols must be distinct simple identifiers")
    frames = {symbol: pd.read_csv(args.data_dir / f"{symbol}.csv") for symbol in symbols}
    asset_types = json.loads(args.asset_types_json.read_text(encoding="utf-8"))
    splits = {}
    for prefix in ("train", "val", "test"):
        for suffix in ("start", "end"):
            value = getattr(args, f"{prefix}_{suffix}")
            if value is not None:
                splits[f"{prefix}{suffix.title()}Date"] = value.isoformat()
    costs = TradingCosts(
        commission_pct=args.commission_pct,
        stamp_duty_pct=args.stamp_duty_pct,
        slippage_pct=args.slippage_pct,
        stamp_duty_mode=args.stamp_duty_mode,
    )
    destination = train_portfolio(
        frames,
        asset_types=asset_types,
        trading_costs=costs,
        splits=splits,
        output_root=args.output_root,
        run_id=args.run_id,
        algo=args.algo,
        total_timesteps=args.steps,
        max_seconds=args.max_seconds,
        episode_bars=args.episode_bars,
        seed=args.seed,
    )
    print(
        json.dumps({"bundle": str(destination), "purpose": "local_smoke_only"}, ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
