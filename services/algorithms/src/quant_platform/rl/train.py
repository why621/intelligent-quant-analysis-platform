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
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from quant_platform.backtesting.execution import EXECUTION_VERSION
from quant_platform.rl import features
from quant_platform.rl.errors import RLError, RLInsufficientHistory, RLInvalidSplit
from quant_platform.rl.policies import RL_POLICIES
from quant_platform.rl.splits import MIN_VALIDATION_BARS, Split, require_regime_coverage
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
    windows: Mapping[str, str] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a schema-complete manifest. Pure and unit-testable without torch.

    ``windows`` carries the CR-052 train/validation/test interval record; the
    caller-provided training dates stay authoritative so bundles written by the
    older single-window callers keep the same shape.
    """
    return {
        "executionVersion": EXECUTION_VERSION,
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
        **(windows or {}),
        "totalTimesteps": int(total_timesteps),
        "codeSha": code_sha,
        "consistency": publication_context.get("consistency", "published_snapshot"),
        **(extra or {}),
    }


def _training_provider(publication_root: Path, history_root: Path | None):
    """Resolve where training bars come from, keeping provenance explicit.

    ``history_root`` is a research-only backfill cache (see
    ``quant_platform.data.deep_history``). It has no immutable publication, so
    the bundle records ``research_backfill_unpublished`` and the web deployment
    gate refuses it — those weights are research evidence, not a release.
    """
    if history_root is not None:
        from quant_platform.data.akshare_provider import AkShareMarketDataProvider

        provider = AkShareMarketDataProvider(data_dir=history_root)
        provider.allow_research_calendar = True
        return provider
    from quant_platform.data.publication import load_publication

    return load_publication(publication_root)


def _unpublished_context(provider, *frames) -> dict[str, str]:
    import hashlib

    import pandas as pd

    dates = [pd.Timestamp(frame["date"].max()) for frame in frames if len(frame)]
    if not dates:
        raise RLInvalidSplit("研究缓存中没有可用行情，无法记录数据版本")
    revision = f"research-history:{provider.cache_revision()}"
    return {
        # The snapshot date has to cover every bar the run consumed, including the
        # held-out validation slice, or the manifest claims a younger cutoff than
        # the evidence it was fitted on.
        "publicationDate": max(dates).date().isoformat(),
        # Digest-shaped so the field keeps its contract form; research origin is
        # recorded in consistency, which no published snapshot can claim.
        "dataVersion": hashlib.sha256(revision.encode("utf-8")).hexdigest(),
        "universeVersion": "research-backfill-root",
        "consistency": "research_backfill_unpublished",
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
    val_start: date | None = None,
    val_end: date | None = None,
    test_start: date | None = None,
    test_end: date | None = None,
    history_root: Path | None = None,
    require_regimes: bool = False,
    threads: int = 1,
    eval_freq: int = 10_000,
    progress_every: int = 5_000,
    overwrite: bool = False,
    hyper_overrides: Mapping[str, object] | None = None,
) -> Path:
    """Train one model and persist its bundle; returns the model directory.

    ``provider`` may be injected (must expose ``history(symbol,start,end,adjust)``
    and a ``publication_context`` mapping) so the training path is testable
    without a full research release; when omitted it loads the immutable
    publication under ``publication_root``, or the research cache under
    ``history_root``.

    The window gate runs before torch is imported: an invalid split must fail
    instantly instead of after minutes of training.

    Production-training additions (T-035d prep, local branch only):
    ``threads`` sizes torch for one run inside a parallel grid; ``eval_freq``
    scores the deterministic policy on the held-out validation window every N
    steps and keeps the best checkpoint (``weightSelection`` records which
    weights were saved); ``progress_every`` prints flushed status lines for
    nohup logs; ``overwrite`` must be explicit to replace an existing run-id;
    ``hyper_overrides`` tunes without editing the spec registry.
    """
    split = Split(start, end, val_start, val_end, test_start, test_end)

    store = ModelStore(models_root)
    if store.exists(run_id) and not overwrite:
        raise RLError(
            f"run-id {run_id!r} 已存在权重，拒绝静默覆盖；换 run-id 或显式 --overwrite"
        )

    try:
        import torch
        from stable_baselines3 import DDPG, DQN, PPO, SAC
    except ImportError as exc:  # pragma: no cover - only without [rl]
        from quant_platform.rl.errors import RLDependenciesMissing

        raise RLDependenciesMissing(
            "训练需要 RL extras：pip install -e \"services/algorithms[rl]\""
        ) from exc

    from quant_platform.rl.env import TradingEnv
    from quant_platform.rl.progress import make_progress_callback

    torch.manual_seed(seed)
    torch.set_num_threads(max(1, int(threads)))

    spec = RL_POLICIES[algo]
    hyperparameters = {**dict(spec.hyperparameters), **(hyper_overrides or {})}
    if provider is None:
        provider = _training_provider(publication_root, history_root)
    prices = provider.history(symbol, start, end, "qfq")
    if prices is None or len(prices) == 0:
        raise RLInsufficientHistory(f"{symbol} 在 {start}..{end} 没有可用行情，拒绝训练")

    extra: dict[str, object] = {}
    observed = [prices]
    if require_regimes:
        extra["regimeCoverage"] = require_regime_coverage(prices)
    held_out = None
    if val_start is not None:
        held_out = provider.history(symbol, val_start, val_end, "qfq")
        observed.append(held_out)
        validation_bars = 0 if held_out is None else len(held_out)
        if validation_bars < MIN_VALIDATION_BARS:
            raise RLInvalidSplit(
                f"验证区间 {val_start}..{val_end} 只有 {validation_bars} 根行情，"
                f"不足 {MIN_VALIDATION_BARS} 根，不能充当留出证据"
            )
        extra["validationBars"] = int(validation_bars)

    env = TradingEnv(prices, discrete=spec.discrete)
    classes = {"DQN": DQN, "PPO": PPO, "SAC": SAC, "DDPG": DDPG}
    model = classes[spec.sb3_class](
        "MlpPolicy", env, seed=seed, verbose=0, **hyperparameters
    )

    eval_cb = None
    log_dir = store.root / "_trainlogs" / run_id
    if held_out is not None and eval_freq > 0:
        from stable_baselines3.common.callbacks import EvalCallback

        log_dir.mkdir(parents=True, exist_ok=True)
        eval_env = TradingEnv(held_out, discrete=spec.discrete)
        eval_cb = EvalCallback(
            eval_env,
            best_model_save_path=str(log_dir),
            log_path=str(log_dir),
            eval_freq=max(1, int(eval_freq)),
            n_eval_episodes=1,
            deterministic=True,
        )
    callbacks = [make_progress_callback(total_timesteps, progress_every, eval_cb=eval_cb)]
    if eval_cb is not None:
        callbacks.append(eval_cb)

    model.learn(total_timesteps=int(total_timesteps), callback=callbacks)

    learned_steps = int(getattr(model, "num_timesteps", total_timesteps))
    updates = int(getattr(model, "_n_updates", 0))
    if updates == 0:
        raise RLError(
            f"{algo} 跑完 {learned_steps} 步但梯度更新为 0"
            "（步数低于 learning_starts 或配置错误），拒绝保存空权重"
        )

    selection = "final"
    best_reward = None
    if eval_cb is not None and (log_dir / "best_model.zip").exists():
        model = classes[spec.sb3_class].load(log_dir / "best_model.zip")
        selection = "validation-best"
        best_reward = float(eval_cb.best_mean_reward)

    context = getattr(provider, "publication_context", None)
    if context is None:
        context = _unpublished_context(provider, *observed)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        model.save(Path(tmp) / "model")
        blob = (Path(tmp) / "model.zip").read_bytes()
    extra.update(
        {
            "symbol": symbol,
            "hyperparameters": hyperparameters,
            "requestedTimesteps": int(total_timesteps),
            "actualTimesteps": learned_steps,
            "gradientUpdates": updates,
            "weightSelection": selection,
            "threads": int(max(1, threads)),
        }
    )
    if best_reward is not None:
        extra["bestEvalReward"] = best_reward
    manifest = assemble_manifest(
        spec=spec,
        run_id=run_id,
        seed=seed,
        train_start=start,
        train_end=end,
        publication_context=context,
        total_timesteps=total_timesteps,
        code_sha=git_code_sha(),
        windows=split.manifest_fields(),
        extra=extra,
    )
    return store.save(run_id, blob, manifest)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_overrides(pairs: list[str] | None) -> dict[str, object]:
    """Parse repeatable ``--set KEY=VALUE`` into a dict; VALUE is JSON when possible."""
    out: dict[str, object] = {}
    for item in pairs or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"--set 需要 KEY=VALUE 形式：{item!r}")
        try:
            out[key.strip()] = json.loads(value)
        except ValueError:
            out[key.strip()] = value
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练单智能体强化学习策略权重")
    parser.add_argument(
        "--publication-root",
        type=Path,
        default=Path(os.environ.get("QUANT_PUBLICATION_ROOT", "")),
    )
    parser.add_argument(
        "--history-root",
        type=Path,
        default=None,
        help="研究专用深历史缓存目录（quant-deep-history 生成）；产出不可上线权重",
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
    parser.add_argument("--val-start", type=_parse_date)
    parser.add_argument("--val-end", type=_parse_date)
    parser.add_argument("--test-start", type=_parse_date)
    parser.add_argument("--test-end", type=_parse_date)
    parser.add_argument(
        "--require-regimes",
        action="store_true",
        help="训练窗口必须实测覆盖牛市、熊市与震荡市",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="torch 线程数；并行网格时每 run 保持 1，靠多进程占满核",
    )
    parser.add_argument(
        "--eval-freq",
        type=int,
        default=10_000,
        help="每 N 步在验证窗上确定性评估并保留最优权重（0=关闭，保存最终权重）",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=5_000,
        help="每 N 步打印一行进度（步数/百分比/耗时/ETA/回合回报）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="允许覆盖同 run-id 的既有权重（默认拒绝）",
    )
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        metavar="KEY=VALUE",
        help="覆盖算法超参，可重复；值按 JSON 解析，如 --set learning_rate=3e-4",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.history_root is None and not str(args.publication_root):
        print(
            json.dumps(
                {"error": "缺少 --publication-root/QUANT_PUBLICATION_ROOT 或 --history-root"},
                ensure_ascii=False,
            )
        )
        return 2
    try:
        overrides = parse_overrides(args.overrides)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "event": "train-start",
                "runId": args.run_id,
                "algo": args.algo,
                "symbol": args.symbol,
                "window": f"{args.start}..{args.end}",
                "validation": f"{args.val_start}..{args.val_end}" if args.val_start else None,
                "test": f"{args.test_start}..{args.test_end}" if args.test_start else None,
                "timesteps": args.timesteps,
                "seed": args.seed,
                "threads": args.threads,
                "evalFreq": args.eval_freq,
                "overrides": overrides or None,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
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
        val_start=args.val_start,
        val_end=args.val_end,
        test_start=args.test_start,
        test_end=args.test_end,
        history_root=args.history_root,
        require_regimes=args.require_regimes,
        threads=args.threads,
        eval_freq=args.eval_freq,
        progress_every=args.progress_every,
        overwrite=args.overwrite,
        hyper_overrides=overrides or None,
    )
    print(json.dumps({"runId": args.run_id, "modelDir": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
