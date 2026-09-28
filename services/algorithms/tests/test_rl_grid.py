"""CR-057 grid orchestration tests. Synthetic prices, never profitability claims.

The fake ``train``/``scorer`` seams exist so the ordering, resume and failure
semantics are testable without torch; the last case runs the real trainer and
the real backtest comparison for one tiny PPO run.
"""

import csv
import json
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_platform.backtesting.execution import EXECUTION_VERSION
from quant_platform.models import BacktestMetrics, BacktestResult
from quant_platform.rl import grid as G
from quant_platform.rl.features import feature_signature
from quant_platform.rl.store import ModelStore

TRAIN_MANIFEST = {
    "executionVersion": EXECUTION_VERSION,
    "algo": "ppo",
    "seed": 42,
    "featureSignature": feature_signature(),
    "publicationDate": "2024-12-31",
    "dataVersion": "data-a",
    "universeVersion": "universe-a",
    "codeSha": "code-a",
    "trainStartDate": "2015-01-01",
    "trainEndDate": "2015-07-31",
    "gradientUpdates": 3,
    "weightSelection": "validation-best",
    "bestEvalReward": 0.5,
    "hyperparameters": {"learning_rate": 3e-4},
}


def _cfg(tmp_path, **over):
    base = dict(
        history_root=tmp_path / "history",
        models_root=tmp_path / "models",
        out_root=tmp_path / "out",
        grid_id="t1",
        symbols=("510300", "510050"),
        algos=("ppo", "dqn"),
        seeds=(42, 43),
    )
    base.update(over)
    return G.GridConfig(**base)


class FakeTrain:
    def __init__(self, store, fail_for=()):
        self.store = store
        self.fail_for = set(fail_for)
        self.calls = []

    def __call__(self, **kw):
        run_id = kw["run_id"]
        self.calls.append(run_id)
        if run_id in self.fail_for:
            raise RuntimeError(f"模拟 {run_id} 训练失败")
        self.store.save(
            run_id, b"fixture", {**TRAIN_MANIFEST, "algo": kw["algo"], "seed": kw["seed"]}
        )
        return self.store.root / run_id


def fake_scorer(cfg, job, provider, store=None):
    row = {
        "totalReturnPct": 1.5,
        "annualizedReturnPct": 1.2,
        "maxDrawdownPct": 0.4,
        "sharpe": 0.9,
        "trades": 2,
        "feesCny": 3.0,
        "costBasis": "engine",
    }
    return {
        job.algo: row,
        "ma_cross": dict(row),
        "momentum_reversal": dict(row),
        "buy_and_hold": {**row, "totalReturnPct": 0.5, "costBasis": "none"},
        "excessVsBuyAndHoldPct": 1.0,
    }


def silent(*args, **kwargs):
    return None


def frame_provider(frame):
    """Minimal duck-typed provider: BacktestEngine and buy_and_hold only call history()."""
    from types import SimpleNamespace

    return SimpleNamespace(history=lambda symbol, start, end, adjust="qfq": frame)


def _rising_frame(days=200):
    dates = pd.date_range("2022-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": 10.0,
            "high": 10.5,
            "low": 9.5,
            "close": np.linspace(10.0, 12.0, days),
        }
    )


def run(tmp_path, **cfg_over):
    store = ModelStore(tmp_path / "models")
    cfg = _cfg(tmp_path, models_root=store.root, **cfg_over)
    fake = FakeTrain(store)
    summary = G.run_grid(cfg, train=fake, scorer=fake_scorer, provider=object(), printer=silent)
    return cfg, fake, summary


class TestExpansion:
    def test_symbol_major_order_and_unique_run_ids(self, tmp_path):
        jobs = G.expand_jobs(_cfg(tmp_path))
        assert [j.run_id for j in jobs] == [
            "ppo-510300-s42",
            "ppo-510300-s43",
            "dqn-510300-s42",
            "dqn-510300-s43",
            "ppo-510050-s42",
            "ppo-510050-s43",
            "dqn-510050-s42",
            "dqn-510050-s43",
        ]
        assert len({j.run_id for j in jobs}) == len(jobs)

    def test_test_window_inside_train_is_refused_before_any_training(self, tmp_path):
        cfg = _cfg(tmp_path, test_start=date(2015, 7, 1))
        with pytest.raises(ValueError, match="留出窗起点"):
            cfg.validate()

    def test_eval_only_conflicts_with_overwrite(self, tmp_path):
        cfg = _cfg(tmp_path, eval_only=True, overwrite=True)
        with pytest.raises(ValueError, match="互斥"):
            cfg.validate()

    def test_unknown_baseline_is_refused(self, tmp_path):
        cfg = _cfg(tmp_path, baselines=("nope",))
        with pytest.raises(ValueError, match="未知基准"):
            cfg.validate()


class TestOrchestration:
    def test_every_job_is_attempted_even_when_one_fails(self, tmp_path):
        store = ModelStore(tmp_path / "models")
        cfg = _cfg(tmp_path, models_root=store.root)
        fake = FakeTrain(store, fail_for={"ppo-510300-s42"})
        summary = G.run_grid(cfg, train=fake, scorer=fake_scorer, provider=object(), printer=silent)
        assert len(fake.calls) == 8  # one failure did not abort the grid
        assert summary["totals"]["ok"] == 7
        assert [f["runId"] for f in summary["failures"]] == ["ppo-510300-s42"]
        assert "模拟" in summary["failures"][0]["error"]

    def test_existing_bundles_are_not_retrained_but_are_still_scored(self, tmp_path):
        store = ModelStore(tmp_path / "models")
        store.save("ppo-510300-s42", b"fixture", TRAIN_MANIFEST)
        cfg = _cfg(tmp_path, models_root=store.root)
        fake = FakeTrain(store)
        summary = G.run_grid(cfg, train=fake, scorer=fake_scorer, provider=object(), printer=silent)
        assert "ppo-510300-s42" not in fake.calls
        assert len(fake.calls) == 7
        assert summary["totals"]["skippedExisting"] == 1
        scored = {r["runId"]: r for r in summary["picks"]["byTestSharpe"]["510300"]}
        assert scored["ppo-510300-s42"]["testSharpe"] == 0.9

    def test_eval_only_trains_nothing_and_scores_what_exists(self, tmp_path):
        store = ModelStore(tmp_path / "models")
        store.save("ppo-510300-s42", b"fixture", TRAIN_MANIFEST)
        cfg = _cfg(
            tmp_path, models_root=store.root, eval_only=True, symbols=("510300",), seeds=(42,)
        )
        fake = FakeTrain(store)
        summary = G.run_grid(cfg, train=fake, scorer=fake_scorer, provider=object(), printer=silent)
        assert fake.calls == []
        assert summary["totals"]["ok"] == 1
        assert summary["totals"]["trained"] == 0

    def test_missing_bundle_surfaces_as_eval_failure(self, tmp_path):
        store = ModelStore(tmp_path / "models")
        cfg = _cfg(tmp_path, models_root=store.root, symbols=("510300",), seeds=(42,))
        summary = G.run_grid(
            cfg,
            train=lambda **kw: None,  # claims success but writes nothing
            scorer=fake_scorer,
            provider=object(),
            printer=silent,
        )
        assert summary["totals"]["ok"] == 0
        assert summary["failures"][0]["status"] == "eval-failed"


class TestArtifacts:
    def test_jsonl_is_line_parseable_and_csv_columns_are_stable(self, tmp_path):
        cfg, _, summary = run(tmp_path)
        lines = Path(summary["artifacts"]["jsonl"]).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 8
        records = [json.loads(line) for line in lines]
        assert [r["runId"] for r in records] == [j.run_id for j in G.expand_jobs(cfg)]
        assert all(r["gridId"] == "t1" for r in records)
        with Path(summary["artifacts"]["csv"]).open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert list(rows[0].keys()) == list(G.CSV_COLUMNS)
        assert len(rows) == 8
        assert rows[0]["test_sharpe"] and rows[0]["baseline_buy_and_hold_sharpe"]
        assert rows[0]["hyperparameters"] != ""

    def test_summary_records_selection_on_validation_only(self, tmp_path):
        _, _, summary = run(tmp_path)
        # algo|symbol groups each keep the best-seed candidate; four groups here.
        assert set(summary["picks"]["byValidation"]) == {
            "ppo|510300",
            "dqn|510300",
            "ppo|510050",
            "dqn|510050",
        }
        assert summary["picks"]["byValidation"]["ppo|510300"]["runId"] == "ppo-510300-s42"
        assert summary["config"]["test"] == f"{G.DEFAULT_TEST_START}..{G.DEFAULT_TEST_END}"
        assert summary["config"]["tradingCosts"]["commissionPct"] == 0.03
        assert summary["caveats"]

    def test_progress_suffix_names_the_baseline_and_shows_activity(self):
        record = {
            "status": "ok",
            "algo": "ppo",
            "bundle": {"bestEvalReward": 0.25},
            "test": {
                "ppo": {"totalReturnPct": -0.02, "trades": 0},
                "buy_and_hold": {"totalReturnPct": -16.6},
                "excessVsBuyAndHoldPct": 16.58,
            },
        }
        line = G._progress_suffix(record)
        assert "买入持有" in line
        assert "0笔" in line  # a flat policy must not read as skill
        assert "超额 16.58pp" in line
        assert "best_val +0.25" in line

    def test_caveats_flag_the_empty_position_reading(self, tmp_path):
        _, _, summary = run(tmp_path)
        assert any("空仓" in caveat for caveat in summary["caveats"])

    def test_failed_run_still_appears_in_the_csv(self, tmp_path):
        store = ModelStore(tmp_path / "models")
        cfg = _cfg(tmp_path, models_root=store.root)
        G.run_grid(
            cfg,
            train=FakeTrain(store, fail_for={"ppo-510300-s42"}),
            scorer=fake_scorer,
            provider=object(),
            printer=silent,
        )
        with (cfg.out_root / "t1-summary.csv").open(encoding="utf-8") as fh:
            rows = {r["run_id"]: r for r in csv.DictReader(fh)}
        assert rows["ppo-510300-s42"]["status"] == "train-failed"
        assert rows["ppo-510300-s42"]["test_sharpe"] == ""
        assert "模拟" in rows["ppo-510300-s42"]["error"]


class TestSameWindowContract:
    """RL and its baselines must be scored on one window, one capital, one cost set."""

    def test_all_requests_share_the_test_window_capital_and_costs(self, tmp_path, monkeypatch):
        captured = []
        metrics = BacktestMetrics(1.0, 2.0, 3.0, 4.0, None, None)
        empty = pd.DataFrame({"date": [], "equity": []})

        class RecordingEngine:
            def __init__(self, provider, strategies):
                self.strategies = strategies

            def run(self, request):
                captured.append(request)
                return BacktestResult(
                    metrics=metrics,
                    equity_curve=empty,
                    trades=(),
                    assumptions={"signalSemantics": "continuous_target_weight"},
                )

        monkeypatch.setattr(G, "BacktestEngine", RecordingEngine)
        cfg = _cfg(tmp_path, symbols=("510300",), seeds=(42,))
        job = G.Job(algo="ppo", symbol="510300", seed=42)
        provider = frame_provider(_rising_frame())
        rows = G.score_run(cfg, job, provider, ModelStore(cfg.models_root))
        assert [r.strategy_id for r in captured] == ["ppo", "ma_cross", "momentum_reversal"]
        assert {r.start_date for r in captured} == {G.DEFAULT_TEST_START}
        assert {r.end_date for r in captured} == {G.DEFAULT_TEST_END}
        assert {r.symbols for r in captured} == {("510300",)}
        assert {r.initial_capital_cny for r in captured} == {cfg.capital}
        assert {r.trading_costs for r in captured} == {cfg.costs}
        assert captured[0].parameters == {"modelRef": "ppo-510300-s42"}
        assert captured[1].parameters == {"shortWindow": 5, "longWindow": 20}
        assert captured[2].parameters["lookback"] == 10
        assert set(rows) == {
            "ppo",
            "ma_cross",
            "momentum_reversal",
            "buy_and_hold",
            "excessVsBuyAndHoldPct",
        }
        assert rows["buy_and_hold"]["costBasis"] == "none"
        assert rows["buy_and_hold"]["trades"] == 0
        assert rows["excessVsBuyAndHoldPct"] == pytest.approx(
            rows["ppo"]["totalReturnPct"] - rows["buy_and_hold"]["totalReturnPct"]
        )

    def test_rl_strategy_instances_are_built_over_the_same_store(self, tmp_path, monkeypatch):
        seen = {}

        class RecordingEngine:
            def __init__(self, provider, strategies):
                seen.update(strategies)

            def run(self, request):
                return BacktestResult(
                    metrics=BacktestMetrics(1.0, 2.0, 3.0, 4.0, None, None),
                    equity_curve=pd.DataFrame({"date": [], "equity": []}),
                    trades=(),
                    assumptions={"signalSemantics": "continuous_target_weight"},
                )

        monkeypatch.setattr(G, "BacktestEngine", RecordingEngine)
        cfg = _cfg(tmp_path, symbols=("510300",), seeds=(42,))
        rows = G.score_run(
            cfg,
            G.Job("ppo", "510300", 42),
            frame_provider(_rising_frame(200)),
            ModelStore(cfg.models_root),
        )
        assert set(seen) == {"ppo", "dqn", "sac", "ddpg", "ma_cross", "momentum_reversal"}
        assert seen["ppo"].rebalance_band_pct == cfg.rebalance_band_pct
        assert seen["ppo"].min_trade_cny == cfg.min_trade_cny
        assert seen["ma_cross"].info().category == "traditional"
        assert rows["buy_and_hold"]["bars"] == 200


class TestCommandLine:
    def test_flags_reach_the_config(self, tmp_path):
        cfg = G.config_from_args(
            G.build_parser().parse_args(
                [
                    "--history-root",
                    str(tmp_path / "h"),
                    "--models-root",
                    str(tmp_path / "m"),
                    "--symbols",
                    "510300",
                    "510050",
                    "--algos",
                    "ppo",
                    "dqn",
                    "--seeds",
                    "7",
                    "8",
                    "--timesteps",
                    "4096",
                    "--capital",
                    "25000",
                    "--slippage-pct",
                    "0.1",
                    "--no-require-regimes",
                    "--set",
                    "learning_rate=1e-4",
                ]
            )
        )
        assert cfg.symbols == ("510300", "510050")
        assert cfg.algos == ("ppo", "dqn")
        assert cfg.seeds == (7, 8)
        assert cfg.timesteps == 4096
        assert cfg.capital == 25000.0
        assert cfg.costs.slippage_pct == 0.1
        assert cfg.require_regimes is False
        assert cfg.hyper_overrides == {"learning_rate": 1e-4}
        # Out default is a folder beside the weights, so one grid stays one tree.
        assert cfg.out_root == cfg.models_root / "_grid"

    def test_window_flags_are_honoured(self, tmp_path):
        cfg = G.config_from_args(
            G.build_parser().parse_args(
                [
                    "--history-root",
                    str(tmp_path),
                    "--test-start",
                    "2030-01-01",
                ]
            )
        )
        assert cfg.test_start == date(2030, 1, 1)

    def test_exit_code_is_nonzero_when_any_run_failed(self, monkeypatch, capsys):
        monkeypatch.setattr(
            G,
            "run_grid",
            lambda cfg: {
                "totals": {"jobs": 2, "failed": 1},
                "picks": {},
                "failures": [{"runId": "dqn-x-s42", "status": "train-failed", "error": "boom"}],
                "artifacts": {"jsonl": "a", "csv": "b", "json": "c"},
            },
        )
        assert G.main(["--history-root", "."]) == 1
        assert "dqn-x-s42" in capsys.readouterr().out

    def test_exit_code_is_zero_when_every_run_scored(self, monkeypatch):
        monkeypatch.setattr(
            G,
            "run_grid",
            lambda cfg: {
                "totals": {"jobs": 1, "failed": 0},
                "picks": {},
                "failures": [],
                "artifacts": {"jsonl": "a", "csv": "b", "json": "c"},
            },
        )
        assert G.main(["--history-root", "."]) == 0


class TestParallel:
    """The pool path, with a synchronous stand-in so no real worker is needed."""

    class FakePool:
        def __init__(self, break_after=None):
            self.submitted = []
            self.break_after = break_after

        def submit(self, fn, *args, **kwargs):
            self.submitted.append(kwargs["index"])
            future = Future()
            if self.break_after is not None and len(self.submitted) > self.break_after:
                future.set_exception(BrokenProcessPool("worker 被 OOM 杀掉"))
            else:
                future.set_result(fn(*args, **kwargs))
            return future

    def _wire(self, tmp_path, monkeypatch):
        store = ModelStore(tmp_path / "models")
        monkeypatch.setattr(G, "train_run", FakeTrain(store))
        monkeypatch.setattr(G, "score_run", fake_scorer)
        monkeypatch.setattr(G, "_training_provider", lambda root, history=None: object())
        return store

    def test_pool_receives_every_job_exactly_once(self, tmp_path, monkeypatch):
        store = self._wire(tmp_path, monkeypatch)
        pool = self.FakePool()
        cfg = _cfg(tmp_path, models_root=store.root, parallel=3)
        summary = G.run_grid(cfg, executor=pool, printer=silent)
        assert sorted(pool.submitted) == list(range(1, 9))
        assert summary["totals"]["ok"] == 8
        assert summary["totals"]["failed"] == 0
        assert summary["config"]["parallel"] == 3

    def test_broken_pool_records_the_unrun_jobs_instead_of_losing_them(
        self, tmp_path, monkeypatch
    ):
        store = self._wire(tmp_path, monkeypatch)
        pool = self.FakePool(break_after=2)
        cfg = _cfg(tmp_path, models_root=store.root, parallel=8)
        summary = G.run_grid(cfg, executor=pool, printer=silent)
        # Which futures the parent got to read before the pool died is not
        # ordered, so the contract is only: nothing is lost, and the survivors
        # are marked as not-run so a re-run resumes instead of silently skipping.
        statuses = {r["runId"]: r["status"] for r in summary["failures"]}
        assert statuses
        assert set(statuses.values()) == {"not-run"}
        assert summary["totals"]["ok"] + len(statuses) == 8
        assert "进程池已损坏" in summary["failures"][0]["error"]
        lines = Path(summary["artifacts"]["jsonl"]).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 8  # every job is still accounted for on disk
        assert len({json.loads(line)["runId"] for line in lines}) == 8

    def test_tables_are_re_sorted_into_job_order(self, tmp_path):
        cfg = _cfg(tmp_path, grid_id="order")
        results = G.GridResults(cfg.out_root, cfg.grid_id)
        for run_id in ["c", "a", "b"]:
            results.append(
                {
                    "gridId": "order",
                    "index": {"c": 3, "a": 1, "b": 2}[run_id],
                    "runId": run_id,
                    "algo": "ppo",
                    "symbol": "510300",
                    "seed": 42,
                    "timesteps": cfg.timesteps,
                    "status": "ok",
                }
            )
        results.write_reports(cfg, [])
        results.close()
        with (cfg.out_root / "order-summary.csv").open(encoding="utf-8") as fh:
            assert [r["run_id"] for r in csv.DictReader(fh)] == ["a", "b", "c"]

    def test_parallel_must_be_at_least_one(self, tmp_path):
        with pytest.raises(ValueError, match="parallel"):
            _cfg(tmp_path, parallel=0).validate()

    def test_parallel_flag_reaches_the_config(self, tmp_path):
        args = G.build_parser().parse_args(["--history-root", str(tmp_path), "--parallel", "14"])
        assert G.config_from_args(args).parallel == 14


class TestRealTinyRun:
    """One genuine PPO run through the real trainer and the real comparison."""

    def test_train_then_score_against_baselines(self, tmp_path, capsys):
        pytest.importorskip("stable_baselines3")
        pytest.importorskip("gymnasium")
        import torch

        torch.set_num_threads(1)
        master = self._master()
        provider = self.WindowProvider(master)
        store = ModelStore(tmp_path / "models")
        cfg = G.GridConfig(
            history_root=tmp_path / "history",
            models_root=store.root,
            out_root=tmp_path / "out",
            grid_id="real",
            symbols=("synth",),
            algos=("ppo",),
            seeds=(42,),
            train_start=date(2015, 1, 1),
            train_end=date(2018, 6, 30),
            val_start=date(2018, 7, 1),
            val_end=date(2019, 7, 31),
            test_start=date(2019, 8, 1),
            test_end=date(2020, 7, 31),
            timesteps=2048,
            eval_freq=2048,
            progress_every=1024,
            require_regimes=False,
        )
        lines = []
        summary = G.run_grid(cfg, provider=provider, printer=lambda *a, **k: lines.append(a[0]))
        assert summary["failures"] == []
        assert summary["totals"] == {
            "jobs": 1,
            "attempted": 1,
            "ok": 1,
            "failed": 0,
            "trained": 1,
            "skippedExisting": 0,
        }
        assert (store.root / "ppo-synth-s42" / "model.zip").exists()
        record = json.loads(Path(summary["artifacts"]["jsonl"]).read_text(encoding="utf-8"))
        assert record["bundle"]["gradientUpdates"] >= 1
        assert record["bundle"]["weightSelection"] == "validation-best"
        # The real trainer's own per-run progress still reaches stdout; the grid
        # adds its own wrapper lines around it.
        trainer_lines = capsys.readouterr().out
        assert "[2048/2048 100.0%]" in trainer_lines
        assert any(line.startswith("[grid 1/1") for line in lines)
        test = record["test"]
        assert set(test) == {
            "ppo",
            "ma_cross",
            "momentum_reversal",
            "buy_and_hold",
            "excessVsBuyAndHoldPct",
        }
        assert test["buy_and_hold"]["bars"] == len(pd.date_range(cfg.test_start, cfg.test_end))
        for row in (test["ppo"], test["ma_cross"], test["momentum_reversal"], test["buy_and_hold"]):
            assert np.isfinite(row["sharpe"])
        with (cfg.out_root / "real-summary.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1 and rows[0]["status"] == "ok"
        assert float(rows[0]["test_trades"]) >= 0

    def test_two_real_workers_share_nothing_but_the_cache(self, tmp_path):
        """A genuine process pool against the research cache, if it is present.

        Spawn/fork is exactly what a fake executor cannot prove: the child has
        to rebuild its own provider and store from the pickled config.
        """
        pytest.importorskip("stable_baselines3")
        pytest.importorskip("gymnasium")
        cache = Path(__file__).resolve().parents[3] / "data/research_history"
        if not (cache / "market_data.db").exists():
            pytest.skip(f"研究缓存不在 {cache}，真实多进程用例需要它")
        import torch

        torch.set_num_threads(1)
        store = ModelStore(tmp_path / "models")
        cfg = G.GridConfig(
            history_root=cache,
            models_root=store.root,
            out_root=tmp_path / "out",
            grid_id="pool",
            symbols=("510300",),
            algos=("ppo",),
            seeds=(42, 43),
            timesteps=2048,
            eval_freq=2048,
            progress_every=2048,
            parallel=2,
        )
        summary = G.run_grid(cfg, printer=silent)
        assert summary["failures"] == []
        assert summary["totals"]["ok"] == 2
        assert (store.root / "ppo-510300-s42" / "model.zip").exists()
        assert (store.root / "ppo-510300-s43" / "model.zip").exists()
        # Two workers must not hand each other a half-written bundle.
        lines = [
            json.loads(line)
            for line in Path(summary["artifacts"]["jsonl"]).read_text(encoding="utf-8").splitlines()
        ]
        assert len({r["bundle"]["bundleHash"] for r in lines}) == 2
        with (cfg.out_root / "pool-summary.csv").open(encoding="utf-8") as fh:
            assert [r["run_id"] for r in csv.DictReader(fh)] == ["ppo-510300-s42", "ppo-510300-s43"]

    class WindowProvider:
        publication_context = {
            "publicationDate": "2020-07-31",
            "universeVersion": "grid-test",
            "dataVersion": "b" * 64,
            "consistency": "synthetic_grid_smoke",
        }

        def __init__(self, master):
            self._master = master

        def cache_revision(self):
            return "grid-test"

        def history(self, symbol, start, end, adjust="qfq"):
            frame = self._master
            return frame[
                (frame.date >= pd.Timestamp(start)) & (frame.date <= pd.Timestamp(end))
            ].reset_index(drop=True)

    @staticmethod
    def _master(rows=2100, seed=7):
        rng = np.random.default_rng(seed)
        close = 100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.01, size=rows))
        dates = pd.date_range(date(2015, 1, 1), periods=rows, freq="D")
        return pd.DataFrame(
            {
                "date": dates,
                "open": close * (1 + rng.normal(0, 0.002, rows)),
                "high": close * (1 + rng.uniform(0.004, 0.012, rows)),
                "low": close * (1 - rng.uniform(0.004, 0.012, rows)),
                "close": close,
            }
        )
