"""Sequential research grid: train the four RL algorithms, then score every
bundle out-of-sample against fixed baselines on the held-out test window.

This is a research driver, not a release path: it reads the deep-history
backfill cache, so the bundles it produces carry
``research_backfill_unpublished`` and the web deployment gate keeps refusing
them. Every number it writes is an offline measurement.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from quant_platform.backtesting.engine import BacktestEngine, _compute_metrics
from quant_platform.models import BacktestRequest, TradingCosts
from quant_platform.rl.policies import RL_POLICIES, RLStrategy
from quant_platform.rl.progress import _fmt
from quant_platform.rl.store import ModelStore
from quant_platform.rl.train import _training_provider, parse_overrides, train_run
from quant_platform.strategies.ma_cross import MACrossStrategy
from quant_platform.strategies.momentum_reversal import MomentumReversalStrategy

DEFAULT_SYMBOLS = ("510300", "510050", "159922")
DEFAULT_ALGOS = ("ppo", "dqn", "sac", "ddpg")
DEFAULT_SEEDS = (42, 43, 44)
# The split agreed with the backfilled research cache (CR-057); the trainer
# re-checks every window against the bars actually on disk.
DEFAULT_TRAIN_START = date(2015, 1, 5)
DEFAULT_TRAIN_END = date(2019, 12, 31)
DEFAULT_VAL_START = date(2020, 1, 2)
DEFAULT_VAL_END = date(2021, 12, 31)
DEFAULT_TEST_START = date(2022, 1, 1)
DEFAULT_TEST_END = date(2024, 12, 31)

BASELINE_STRATEGIES: Mapping[str, tuple[type, Mapping[str, object]]] = {
    "ma_cross": (MACrossStrategy, {"shortWindow": 5, "longWindow": 20}),
    "momentum_reversal": (
        MomentumReversalStrategy,
        {"lookback": 10, "overboughtThreshold": 5.0, "oversoldThreshold": -5.0},
    ),
}

CAVEATS = (
    "买入持有基准不计交易成本，RL 与均线/动量策略按引擎费率计成本，"
    "excessVsBuyAndHoldPct 因此略偏乐观",
    "test 窗是唯一留出窗；跨标的跨算法的最优值是从全部候选里挑出来的，存在选择偏差，不构成收益承诺",
    "网格 ETA 由已完成 job 的实测均值外推；off-policy 前段每步更便宜，早期数值偏乐观",
    "权重来自 research_backfill_unpublished 研究缓存，仅供离线研究，Web 部署闸门会拒绝",
    "推理侧仍不校验请求标的与训练标的是否一致（缺陷 #5 未修）；本网格每个 run 只回测其自身标的",
    "接近空仓的策略在下跌的基准上会显示为大幅超额；读 excessVsBuyAndHoldPct 前先看 trades 与 "
    "testMaxDrawdownPct，成交笔数接近 0 的“跑赢”不是技能",
)

CSV_COLUMNS = (
    "grid_id",
    "run_id",
    "algo",
    "symbol",
    "seed",
    "status",
    "train_skipped",
    "timesteps",
    "gradient_updates",
    "weight_selection",
    "best_eval_reward",
    "test_total_return_pct",
    "test_annualized_return_pct",
    "test_max_drawdown_pct",
    "test_sharpe",
    "test_trades",
    "test_fees_cny",
    "baseline_buy_and_hold_total_return_pct",
    "baseline_buy_and_hold_sharpe",
    "baseline_ma_cross_total_return_pct",
    "baseline_ma_cross_sharpe",
    "baseline_momentum_reversal_total_return_pct",
    "baseline_momentum_reversal_sharpe",
    "excess_vs_buy_and_hold_pct",
    "wall_seconds",
    "hyperparameters",
    "error",
)


@dataclass(frozen=True)
class Job:
    algo: str
    symbol: str
    seed: int

    @property
    def run_id(self) -> str:
        return f"{self.algo}-{self.symbol}-s{self.seed}"


@dataclass
class GridConfig:
    history_root: Path
    models_root: Path
    out_root: Path
    grid_id: str
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    algos: tuple[str, ...] = DEFAULT_ALGOS
    seeds: tuple[int, ...] = DEFAULT_SEEDS
    train_start: date = DEFAULT_TRAIN_START
    train_end: date = DEFAULT_TRAIN_END
    val_start: date = DEFAULT_VAL_START
    val_end: date = DEFAULT_VAL_END
    test_start: date = DEFAULT_TEST_START
    test_end: date = DEFAULT_TEST_END
    timesteps: int = 200_000
    eval_freq: int = 20_000
    progress_every: int = 10_000
    threads: int = 1
    require_regimes: bool = True
    hyper_overrides: Mapping[str, object] = field(default_factory=dict)
    overwrite: bool = False
    eval_only: bool = False
    capital: float = 100_000.0
    costs: TradingCosts = field(default_factory=TradingCosts)
    rebalance_band_pct: float = 0.005
    min_trade_cny: float = 100.0
    baselines: tuple[str, ...] = tuple(BASELINE_STRATEGIES)

    def validate(self) -> None:
        unknown_algo = set(self.algos) - set(RL_POLICIES)
        if unknown_algo:
            raise ValueError(f"未知算法: {sorted(unknown_algo)}")
        unknown_baseline = set(self.baselines) - set(BASELINE_STRATEGIES)
        if unknown_baseline:
            raise ValueError(f"未知基准: {sorted(unknown_baseline)}")
        if not self.symbols or not self.algos or not self.seeds:
            raise ValueError("symbols/algos/seeds 都不能为空")
        if self.test_start <= self.train_end:
            raise ValueError(
                f"留出窗起点 {self.test_start} 不晚于训练窗终点 {self.train_end}，"
                "会把 test 设进训练区间"
            )
        if self.test_start <= self.val_end:
            raise ValueError(f"留出窗起点 {self.test_start} 不晚于验证窗终点 {self.val_end}")
        if self.eval_only and self.overwrite:
            raise ValueError("--eval-only 与 --overwrite 互斥")

    @property
    def test_window(self) -> tuple[date, date]:
        return (self.test_start, self.test_end)


def expand_jobs(cfg: GridConfig) -> list[Job]:
    """Symbol-major so a whole symbol's models land together in the log."""
    return [
        Job(algo=a, symbol=s, seed=int(seed))
        for s in cfg.symbols
        for a in cfg.algos
        for seed in cfg.seeds
    ]


def _metrics_row(metrics, trades) -> dict[str, object]:
    return {
        "totalReturnPct": round(metrics.total_return_pct, 4),
        "annualizedReturnPct": round(metrics.annualized_return_pct, 4),
        "maxDrawdownPct": round(metrics.max_drawdown_pct, 4),
        "sharpe": round(metrics.sharpe, 4),
        "trades": len(trades),
        "feesCny": round(float(sum(t.fee_cny for t in trades)), 2),
        "costBasis": "engine",
    }


def buy_and_hold(cfg: GridConfig, job: Job, provider) -> dict[str, object]:
    """The reference an ETF buyer actually had: hold the same bars, no signals.

    Cost-free by construction — the honest comparison point is the asset, not
    another strategy's turnover.
    """
    prices = provider.history(job.symbol, *cfg.test_window, "qfq")
    if prices is None or prices.empty:
        raise ValueError(f"{job.symbol} 在留出窗没有可用行情")
    close = (
        prices.assign(date=pd.to_datetime(prices["date"]))
        .set_index("date")["close"]
        .astype(float)
        .sort_index()
    )
    equity = cfg.capital * close / float(close.iloc[0])
    metrics = _compute_metrics(equity, None, cfg.capital)
    return {
        **_metrics_row(metrics, ()),
        "costBasis": "none",
        "bars": int(len(close)),
    }


def score_run(cfg: GridConfig, job: Job, provider, store: ModelStore | None = None) -> dict:
    """One RL bundle vs the baselines on the identical window, capital and costs."""
    store = store or ModelStore(cfg.models_root)
    strategies: dict[str, object] = {
        sid: RLStrategy(
            spec,
            store=store,
            rebalance_band_pct=cfg.rebalance_band_pct,
            min_trade_cny=cfg.min_trade_cny,
        )
        for sid, spec in RL_POLICIES.items()
    }
    for baseline_id, (cls, _params) in BASELINE_STRATEGIES.items():
        strategies[baseline_id] = cls()
    engine = BacktestEngine(provider, strategies)
    rows: dict[str, object] = {}

    def _request(strategy_id: str, parameters: Mapping[str, object]) -> BacktestRequest:
        return BacktestRequest(
            symbols=(job.symbol,),
            strategy_id=strategy_id,
            start_date=cfg.test_start,
            end_date=cfg.test_end,
            parameters=dict(parameters),
            initial_capital_cny=cfg.capital,
            trading_costs=cfg.costs,
        )

    rl = engine.run(_request(job.algo, {"modelRef": job.run_id}))
    rows[job.algo] = _metrics_row(rl.metrics, rl.trades)
    rows[job.algo]["signalSemantics"] = rl.assumptions.get("signalSemantics")
    for baseline_id in cfg.baselines:
        result = engine.run(_request(baseline_id, BASELINE_STRATEGIES[baseline_id][1]))
        rows[baseline_id] = _metrics_row(result.metrics, result.trades)
    rows["buy_and_hold"] = buy_and_hold(cfg, job, provider)
    rows["excessVsBuyAndHoldPct"] = round(
        float(rows[job.algo]["totalReturnPct"]) - float(rows["buy_and_hold"]["totalReturnPct"]), 4
    )
    return rows


def _bundle_facts(manifest: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "gradientUpdates",
        "weightSelection",
        "bestEvalReward",
        "actualTimesteps",
        "requestedTimesteps",
        "hyperparameters",
        "trainEndDate",
        "valStartDate",
        "valEndDate",
        "executionVersion",
        "featureSignature",
        "dataVersion",
        "bundleHash",
        "codeSha",
    )
    return {k: manifest.get(k) for k in keys}


def _csv_row(cfg: GridConfig, record: dict) -> dict[str, object]:
    test = record.get("test") or {}
    bundle = record.get("bundle") or {}
    algo = record["algo"]

    def _baseline(rid: str, key: str):
        row = test.get(rid)
        return row.get(key) if isinstance(row, dict) else None

    hyper = bundle.get("hyperparameters")
    return {
        "grid_id": cfg.grid_id,
        "run_id": record["runId"],
        "algo": algo,
        "symbol": record["symbol"],
        "seed": record["seed"],
        "status": record["status"],
        "train_skipped": bool(record.get("trainSkipped")),
        "timesteps": record.get("timesteps"),
        "gradient_updates": bundle.get("gradientUpdates"),
        "weight_selection": bundle.get("weightSelection"),
        "best_eval_reward": bundle.get("bestEvalReward"),
        "test_total_return_pct": _row_value(test.get(algo), "totalReturnPct"),
        "test_annualized_return_pct": _row_value(test.get(algo), "annualizedReturnPct"),
        "test_max_drawdown_pct": _row_value(test.get(algo), "maxDrawdownPct"),
        "test_sharpe": _row_value(test.get(algo), "sharpe"),
        "test_trades": _row_value(test.get(algo), "trades"),
        "test_fees_cny": _row_value(test.get(algo), "feesCny"),
        "baseline_buy_and_hold_total_return_pct": _baseline("buy_and_hold", "totalReturnPct"),
        "baseline_buy_and_hold_sharpe": _baseline("buy_and_hold", "sharpe"),
        "baseline_ma_cross_total_return_pct": _baseline("ma_cross", "totalReturnPct"),
        "baseline_ma_cross_sharpe": _baseline("ma_cross", "sharpe"),
        "baseline_momentum_reversal_total_return_pct": _baseline(
            "momentum_reversal", "totalReturnPct"
        ),
        "baseline_momentum_reversal_sharpe": _baseline("momentum_reversal", "sharpe"),
        "excess_vs_buy_and_hold_pct": test.get("excessVsBuyAndHoldPct"),
        "wall_seconds": record.get("wallSeconds"),
        "hyperparameters": json.dumps(hyper, ensure_ascii=False, sort_keys=True) if hyper else "",
        "error": record.get("error", ""),
    }


def _row_value(row, key):
    return row.get(key) if isinstance(row, dict) else None


class GridResults:
    """Append-only jsonl plus the end-of-grid csv/summary pair.

    Each record is flushed immediately: a 36-run grid is hours of CPU, and an
    OOM or a killed session must not cost the runs that already finished.
    """

    def __init__(self, out_root: Path, grid_id: str) -> None:
        out_root.mkdir(parents=True, exist_ok=True)
        self.path = out_root / f"{grid_id}.jsonl"
        self.records: list[dict] = []
        self._fh = self.path.open("a", encoding="utf-8")

    def append(self, record: dict) -> None:
        self.records.append(record)
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def write_reports(self, cfg: GridConfig, jobs: Sequence[Job]) -> dict:
        csv_path = cfg.out_root / f"{cfg.grid_id}-summary.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
            writer.writeheader()
            for record in self.records:
                writer.writerow(_csv_row(cfg, record))
        summary = build_summary(cfg, jobs, self.records)
        json_path = cfg.out_root / f"{cfg.grid_id}-summary.json"
        json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["artifacts"] = {
            "jsonl": str(self.path),
            "csv": str(csv_path),
            "json": str(json_path),
        }
        return summary


def build_summary(cfg: GridConfig, jobs: Sequence[Job], records: Sequence[dict]) -> dict:
    ok = [r for r in records if r["status"] == "ok"]
    failed = [r for r in records if r["status"] != "ok"]
    # Seed choice is made on the validation window only; the test window stays
    # untouched for that decision, so picking by test score would be leakage.
    by_validation: dict[str, dict] = {}
    for record in ok:
        reward = (record.get("bundle") or {}).get("bestEvalReward")
        if reward is None:
            continue
        key = f"{record['algo']}|{record['symbol']}"
        best = by_validation.get(key)
        if best is None or float(reward) > float(best["bestEvalReward"]):
            by_validation[key] = {
                "runId": record["runId"],
                "seed": record["seed"],
                "bestEvalReward": reward,
            }
    ranked: dict[str, list[dict]] = {}
    for record in ok:
        row = record.get("test") or {}
        score = _row_value(row.get(record["algo"]), "sharpe")
        if score is None:
            continue
        ranked.setdefault(record["symbol"], []).append(
            {
                "runId": record["runId"],
                "algo": record["algo"],
                "seed": record["seed"],
                "testSharpe": score,
                "testTotalReturnPct": _row_value(row.get(record["algo"]), "totalReturnPct"),
                "excessVsBuyAndHoldPct": row.get("excessVsBuyAndHoldPct"),
            }
        )
    for rows in ranked.values():
        rows.sort(key=lambda item: float(item["testSharpe"]), reverse=True)
    return {
        "gridId": cfg.grid_id,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "historyRoot": str(cfg.history_root),
            "modelsRoot": str(cfg.models_root),
            "symbols": list(cfg.symbols),
            "algos": list(cfg.algos),
            "seeds": list(cfg.seeds),
            "train": f"{cfg.train_start}..{cfg.train_end}",
            "validation": f"{cfg.val_start}..{cfg.val_end}",
            "test": f"{cfg.test_start}..{cfg.test_end}",
            "timesteps": cfg.timesteps,
            "evalFreq": cfg.eval_freq,
            "threads": cfg.threads,
            "requireRegimes": cfg.require_regimes,
            "hyperOverrides": dict(cfg.hyper_overrides),
            "capital": cfg.capital,
            "tradingCosts": {
                "commissionPct": cfg.costs.commission_pct,
                "stampDutyPct": cfg.costs.stamp_duty_pct,
                "slippagePct": cfg.costs.slippage_pct,
            },
            "rebalanceBandPct": cfg.rebalance_band_pct,
            "minTradeCny": cfg.min_trade_cny,
            "baselines": list(cfg.baselines),
        },
        "totals": {
            "jobs": len(jobs),
            "attempted": len(records),
            "ok": len(ok),
            "failed": len(failed),
            "trained": sum(1 for r in records if not r.get("trainSkipped")),
            "skippedExisting": sum(1 for r in records if r.get("trainSkipped")),
        },
        "failures": [
            {"runId": r["runId"], "status": r["status"], "error": r.get("error")} for r in failed
        ],
        "picks": {"byValidation": by_validation, "byTestSharpe": ranked},
        "caveats": list(CAVEATS),
    }


def run_grid(
    cfg: GridConfig,
    *,
    provider=None,
    train: Callable = train_run,
    scorer: Callable = score_run,
    printer: Callable[[str], None] = print,
) -> dict:
    cfg.validate()
    jobs = expand_jobs(cfg)
    provider = provider or _training_provider(Path(""), cfg.history_root)
    store = ModelStore(cfg.models_root)
    results = GridResults(cfg.out_root, cfg.grid_id)
    total_steps = max(1, cfg.timesteps) * len(jobs)
    done_steps = 0
    grid_start = time.time()
    printer(
        f"[grid {cfg.grid_id}] {len(jobs)} 个 run × {cfg.timesteps} 步 = {total_steps} 步；"
        f"留出窗 {cfg.test_start}..{cfg.test_end}；"
        "ETA 按已完成 run 实测均值外推，早期偏乐观",
        flush=True,
    )
    for index, job in enumerate(jobs, start=1):
        started = time.time()
        record: dict = {
            "gridId": cfg.grid_id,
            "index": index,
            "of": len(jobs),
            "runId": job.run_id,
            "algo": job.algo,
            "symbol": job.symbol,
            "seed": job.seed,
            "timesteps": cfg.timesteps,
            "status": "ok",
        }
        if cfg.eval_only:
            record["trainSkipped"] = True
        elif store.exists(job.run_id) and not cfg.overwrite:
            record["trainSkipped"] = True
        else:
            try:
                train(
                    publication_root=Path(""),
                    models_root=cfg.models_root,
                    run_id=job.run_id,
                    algo=job.algo,
                    symbol=job.symbol,
                    seed=job.seed,
                    start=cfg.train_start,
                    end=cfg.train_end,
                    total_timesteps=cfg.timesteps,
                    provider=provider,
                    val_start=cfg.val_start,
                    val_end=cfg.val_end,
                    test_start=cfg.test_start,
                    test_end=cfg.test_end,
                    require_regimes=cfg.require_regimes,
                    threads=cfg.threads,
                    eval_freq=cfg.eval_freq,
                    progress_every=cfg.progress_every,
                    overwrite=cfg.overwrite,
                    hyper_overrides=cfg.hyper_overrides,
                )
            except Exception as exc:  # one bad run must not cost the whole grid
                record["status"] = "train-failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
        if record["status"] == "ok":
            try:
                record["bundle"] = _bundle_facts(store.load(job.run_id).manifest)
                record["test"] = scorer(cfg, job, provider, store)
            except Exception as exc:
                record["status"] = "eval-failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
        record["wallSeconds"] = round(time.time() - started, 1)
        done_steps += cfg.timesteps
        results.append(record)
        elapsed = time.time() - grid_start
        eta = elapsed / done_steps * (total_steps - done_steps)
        suffix = _progress_suffix(record)
        printer(
            f"[grid {index}/{len(jobs)} {100.0 * done_steps / total_steps:5.1f}%] "
            f"{job.run_id} {record['status']} run用时 {_fmt(record['wallSeconds'])} "
            f"网格已耗时 {_fmt(elapsed)} 网格ETA {_fmt(eta)}{suffix}",
            flush=True,
        )
    summary = results.write_reports(cfg, jobs)
    results.close()
    return summary


def _progress_suffix(record: dict) -> str:
    if record["status"] != "ok":
        return f" | {record.get('error')}"
    test = record.get("test") or {}
    row = test.get(record["algo"]) or {}
    reward = (record.get("bundle") or {}).get("bestEvalReward")
    parts = []
    if row:
        parts.append(
            f"test {row.get('totalReturnPct')}%/{row.get('trades')}笔"
            f" vs 买入持有 {test.get('buy_and_hold', {}).get('totalReturnPct')}%"
            f" (超额 {test.get('excessVsBuyAndHoldPct')}pp)"
        )
    if reward is not None:
        parts.append(f"best_val {reward:+.2f}")
    return (" | " + " | ".join(parts)) if parts else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="依次训练 RL 网格并在留出窗与基准对比，结果增量落盘（研究用途）"
    )
    parser.add_argument("--history-root", required=True, type=Path, help="深历史研究缓存目录")
    parser.add_argument(
        "--models-root",
        type=Path,
        default=Path(__file__).resolve().parents[5] / "models",
    )
    parser.add_argument("--out", type=Path, default=None, help="结果目录，默认 <models-root>/_grid")
    parser.add_argument("--grid-id", default=None)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--algos", nargs="+", default=list(DEFAULT_ALGOS), choices=sorted(RL_POLICIES)
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--start", type=date.fromisoformat, default=DEFAULT_TRAIN_START)
    parser.add_argument("--end", type=date.fromisoformat, default=DEFAULT_TRAIN_END)
    parser.add_argument("--val-start", type=date.fromisoformat, default=DEFAULT_VAL_START)
    parser.add_argument("--val-end", type=date.fromisoformat, default=DEFAULT_VAL_END)
    parser.add_argument("--test-start", type=date.fromisoformat, default=DEFAULT_TEST_START)
    parser.add_argument("--test-end", type=date.fromisoformat, default=DEFAULT_TEST_END)
    parser.add_argument("--timesteps", type=int, default=200_000)
    parser.add_argument("--eval-freq", type=int, default=20_000)
    parser.add_argument("--progress-every", type=int, default=10_000)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--require-regimes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="训练窗必须实测覆盖牛/熊/震荡（默认开启）",
    )
    parser.add_argument("--set", dest="overrides", action="append", metavar="KEY=VALUE")
    parser.add_argument("--overwrite", action="store_true", help="重训同名 run-id 的既有权重")
    parser.add_argument("--eval-only", action="store_true", help="跳过训练，只重新评估既有权重")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--commission-pct", type=float, default=0.03)
    parser.add_argument("--stamp-duty-pct", type=float, default=0.05)
    parser.add_argument("--slippage-pct", type=float, default=0.02)
    parser.add_argument("--rebalance-band-pct", type=float, default=0.005)
    parser.add_argument("--min-trade-cny", type=float, default=100.0)
    parser.add_argument(
        "--baselines",
        nargs="+",
        default=sorted(BASELINE_STRATEGIES),
        choices=sorted(BASELINE_STRATEGIES),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> GridConfig:
    return GridConfig(
        history_root=args.history_root,
        models_root=args.models_root,
        out_root=args.out or args.models_root / "_grid",
        grid_id=args.grid_id or time.strftime("%Y%m%d-%H%M%S"),
        symbols=tuple(args.symbols),
        algos=tuple(args.algos),
        seeds=tuple(args.seeds),
        train_start=args.start,
        train_end=args.end,
        val_start=args.val_start,
        val_end=args.val_end,
        test_start=args.test_start,
        test_end=args.test_end,
        timesteps=args.timesteps,
        eval_freq=args.eval_freq,
        progress_every=args.progress_every,
        threads=args.threads,
        require_regimes=args.require_regimes,
        hyper_overrides=parse_overrides(args.overrides),
        overwrite=args.overwrite,
        eval_only=args.eval_only,
        capital=args.capital,
        costs=TradingCosts(
            commission_pct=args.commission_pct,
            stamp_duty_pct=args.stamp_duty_pct,
            slippage_pct=args.slippage_pct,
        ),
        rebalance_band_pct=args.rebalance_band_pct,
        min_trade_cny=args.min_trade_cny,
        baselines=tuple(args.baselines),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)
    summary = run_grid(cfg)
    artifacts = summary["artifacts"]
    print(
        json.dumps(
            {
                "totals": summary["totals"],
                "failures": summary["failures"],
                "picks": summary["picks"],
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if summary["failures"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
