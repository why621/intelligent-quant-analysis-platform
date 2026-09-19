"""``quant-rl-train`` — offline trainer for the single-agent RL strategies.

Trains from an immutable research publication (never the live cache), pins the
seed and torch threads for reproducibility, and writes the resulting weights +
manifest into the gitignored model store. torch / stable-baselines3 are
imported lazily so this module is import-safe without the ``[rl]`` extra.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from quant_platform.rl import features
from quant_platform.rl.policies import RL_POLICIES
from quant_platform.rl.store import ModelStore


def git_code_sha() -> str:
    try:
        import subprocess

        return subprocess.check_output(  # noqa: S603 - fixed args, local repo only
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()[:40]
    except Exception:  # pragma: no cover - outside a checkout
        return "unknown"


def assemble_manifest(
    *,
    spec,
    run_id: str,
    seed: int,
    train_start: date,
    train_end: date,
    publication_context: dict[str, str],
    total_timesteps: int,
    code_sha: str,
) -> dict[str, object]:
    """Build a schema-complete manifest. Pure and unit-testable without torch."""
    return {
        "runId": run_id,
        "algo": spec.algo_id,
        "sb3Class": spec.sb3_class,
        "seed": int(seed),
        "featureSignature": features.feature_signature(),
        "publicationDate": publication_context["publicationDate"],
        "dataVersion": publication_context["dataVersion"],
        "universeVersion": publication_context["universeVersion"],
        "trainStartDate": train_start.isoformat(),
        "trainEndDate": train_end.isoformat(),
        "totalTimesteps": int(total_timesteps),
        "codeSha": code_sha,
        "consistency": publication_context.get("consistency", "published_snapshot"),
    }


def train_run(
    *,
    publication_root: Path,
    models_root: Path,
    run_id: str,
    algo: str,
    symbol: str,
    start: date,
    end: date,
    seed: int,
    total_timesteps: int,
    provider=None,
) -> Path:
    """Train one model and persist its bundle; returns the model directory.

    ``provider`` may be injected (must expose ``history(symbol,start,end,adjust)``
    and a ``publication_context`` mapping) so the training path is testable
    without a full research release; when omitted it loads the immutable
    publication under ``publication_root``.
    """
    try:
        import torch
        from stable_baselines3 import DDPG, DQN, PPO, SAC
    except ImportError as exc:  # pragma: no cover - only without [rl]
        from quant_platform.rl.errors import RLDependenciesMissing

        raise RLDependenciesMissing(
            "训练需要 RL extras：pip install -e \"services/algorithms[rl]\""
        ) from exc

    from quant_platform.rl.env import TradingEnv

    torch.manual_seed(seed)
    torch.set_num_threads(1)

    spec = RL_POLICIES[algo]
    if provider is None:
        from quant_platform.data.publication import load_publication

        provider = load_publication(publication_root)
    prices = provider.history(symbol, start, end, "qfq")
    env = TradingEnv(prices, discrete=spec.discrete)
    classes = {"DQN": DQN, "PPO": PPO, "SAC": SAC, "DDPG": DDPG}
    model = classes[spec.sb3_class](
        "MlpPolicy", env, seed=seed, verbose=0, **dict(spec.hyperparameters)
    )
    model.learn(total_timesteps=int(total_timesteps))

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        model.save(Path(tmp) / "model")
        blob = (Path(tmp) / "model.zip").read_bytes()
    manifest = assemble_manifest(
        spec=spec,
        run_id=run_id,
        seed=seed,
        train_start=start,
        train_end=end,
        publication_context=provider.publication_context,
        total_timesteps=total_timesteps,
        code_sha=git_code_sha(),
    )
    store = ModelStore(models_root)
    return store.save(run_id, blob, manifest)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练单智能体强化学习策略权重")
    parser.add_argument(
        "--publication-root",
        type=Path,
        default=Path(os.environ.get("QUANT_PUBLICATION_ROOT", "")),
    )
    parser.add_argument(
        "--models-root",
        type=Path,
        default=Path(__file__).resolve().parents[5] / "models",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--algo", required=True, choices=sorted(RL_POLICIES))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, type=_parse_date)
    parser.add_argument("--end", required=True, type=_parse_date)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timesteps", type=int, default=20_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not str(args.publication_root):
        print(
            json.dumps(
                {"error": "缺少 --publication-root 或 QUANT_PUBLICATION_ROOT"},
                ensure_ascii=False,
            )
        )
        return 2
    path = train_run(
        publication_root=args.publication_root,
        models_root=args.models_root,
        run_id=args.run_id,
        algo=args.algo,
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        seed=args.seed,
        total_timesteps=args.timesteps,
    )
    print(json.dumps({"runId": args.run_id, "modelDir": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
