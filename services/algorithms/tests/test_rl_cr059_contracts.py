"""CR-059 contracts: fold selection, reward modes, turnover governance, the
multiple-testing gate, and the train/serve band hand-off.

Split into pure tests (no ``[rl]`` extra, no torch) and heavy ones that skip
without the extras, matching the rest of the ``rl/`` suite. Every assertion here
pins a claim CR-059's acceptance criteria make, so the diagnosis behind the CR
stays checkable rather than becoming folklore.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.backtesting.execution import EXECUTION_VERSION
from quant_platform.models import TradingCosts
from quant_platform.rl import grid as G
from quant_platform.rl import selection as S
from quant_platform.rl.errors import RLIncompatibleModel
from quant_platform.rl.features import MIN_WARMUP, feature_signature
from quant_platform.rl.policies import PPO, RLStrategy
from quant_platform.rl.splits import (
    MIN_VALIDATION_DAYS,
    RLInvalidSplit,
    Split,
    ValFold,
)

# The CR-059 design: three folds tiling 2018-07-01..2021-12-31.
FOLDS = (
    ("2018-07-01", "2019-09-30"),
    ("2019-10-01", "2020-09-30"),
    ("2020-10-01", "2021-12-31"),
)


class TestFoldGate:
    """Acceptance (1): the fold gate is what stops a bull-only validation span."""

    def test_three_folds_derive_the_validation_span(self):
        split = Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                      test_end="2024-12-31", val_folds=FOLDS)
        assert len(split.val_folds) == 3
        assert split.val_start == date(2018, 7, 1)
        assert split.val_end == date(2021, 12, 31)
        # The validation span is in-sample, so serving must refuse to score it.
        assert split.in_sample_end == date(2021, 12, 31)

    def test_each_fold_must_be_one_to_two_years(self):
        for bad in (("2018-07-01", "2019-06-29"), ("2018-07-01", "2020-08-01")):
            with pytest.raises(RLInvalidSplit, match="不在"):
                Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                      test_end="2024-12-31", val_folds=(bad,))
        # The boundary case that forced the CR's fold edges: a calendar-year 2021
        # is 364 days and is correctly refused.
        assert (date(2021, 12, 31) - date(2021, 1, 1)).days == 364
        assert (date(2021, 12, 31) - date(2021, 1, 1)).days < MIN_VALIDATION_DAYS

    def test_overlapping_folds_are_refused(self):
        with pytest.raises(RLInvalidSplit, match="重叠"):
            Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                  test_end="2024-12-31",
                  val_folds=(("2018-07-01", "2019-09-30"), ("2019-09-30", "2020-09-30")))

    def test_fold_must_not_start_inside_training(self):
        with pytest.raises(RLInvalidSplit, match="晚于训练终点"):
            Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                  test_end="2024-12-31", val_folds=(("2018-06-01", "2019-09-30"),))

    def test_fold_must_not_reach_into_the_test_window(self):
        with pytest.raises(RLInvalidSplit, match="早于测试起点"):
            Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                  test_end="2024-12-31", val_folds=(("2020-10-01", "2022-06-30"),))

    def test_folds_round_trip_through_the_manifest(self):
        from quant_platform.rl.splits import split_from_manifest

        split = Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                      test_end="2024-12-31", val_folds=FOLDS)
        fields = split.manifest_fields()
        assert fields["valFolds"] == [
            {"start": start, "end": end} for start, end in FOLDS
        ]
        assert split_from_manifest(fields).val_folds == split.val_folds

    def test_val_fold_accepts_a_tuple_or_an_object(self):
        assert ValFold("2018-07-01", "2019-09-30").span_days == 456
        split = Split("2015-01-05", "2018-06-30", test_start="2022-01-01",
                      test_end="2024-12-31",
                      val_folds=(ValFold("2018-07-01", "2019-09-30"),))
        assert split.val_folds[0].end == date(2019, 9, 30)


class TestNoiseThreshold:
    """Acceptance (7): without this number, best-of-N reads as skill."""

    T = 726  # the held-out window's daily bars

    def test_expected_max_matches_hand_computation(self):
        # Bailey & Lopez de Prado's E[max SR] approximation, in standard-error units.
        assert S.expected_max_standard_errors(1) == 0.0  # no selection, no inflation
        assert S.expected_max_standard_errors(4) == pytest.approx(1.0521, abs=5e-5)
        assert S.expected_max_standard_errors(12) == pytest.approx(1.6648, abs=5e-5)
        assert S.expected_max_standard_errors(36) == pytest.approx(2.1475, abs=5e-5)

    def test_annualised_thresholds_match_hand_computation(self):
        assert S.noise_sharpe_threshold(4, self.T) == pytest.approx(0.6199, abs=5e-5)
        assert S.noise_sharpe_threshold(12, self.T) == pytest.approx(0.9808, abs=5e-5)
        assert S.noise_sharpe_threshold(36, self.T) == pytest.approx(1.2652, abs=5e-5)

    def test_the_measured_grid_winner_does_not_clear_the_threshold(self):
        """The actual CR-058 result: best of 12 was 0.761 on 726 bars."""
        verdict = S.deflate(0.761, self.T, 12)
        assert verdict.clears is False
        assert verdict.threshold == pytest.approx(0.9808, abs=5e-5)
        # A probability at or below 0.5 means indistinguishable from noise.
        assert verdict.deflated_probability <= 0.5

    def test_threshold_grows_with_trials_and_shrinks_with_sample(self):
        assert S.noise_sharpe_threshold(36, self.T) > S.noise_sharpe_threshold(4, self.T)
        assert S.noise_sharpe_threshold(12, 200) > S.noise_sharpe_threshold(12, 2000)

    def test_median_fold_score_is_the_median_not_the_mean(self):
        assert S.median_fold_score([2.0, 0.1, 0.2]) == pytest.approx(0.2)
        with pytest.raises(ValueError):
            S.median_fold_score([])

    def test_min_track_record_length_is_a_floor(self):
        assert S.min_track_record_length(0.0) == float("inf")
        # 0.761 annualised needs years of bars before it is significant at 95%.
        assert S.min_track_record_length(0.761) > self.T


class TestSummaryContracts:
    """Acceptance (7) again, at the artifact level: the warning ships with the numbers."""

    def _summary(self, tmp_path, sharpe=0.30):
        self._sharpe = sharpe
        store_path = tmp_path / "models"
        store = G.ModelStore(store_path)
        manifest = {
            "executionVersion": EXECUTION_VERSION,
            "algo": "ppo",
            "seed": 42,
            "featureSignature": feature_signature(),
            "publicationDate": "2024-12-31",
            "dataVersion": "d",
            "universeVersion": "u",
            "codeSha": "c",
            "trainStartDate": "2015-01-05",
            "trainEndDate": "2018-06-30",
            "bandPct": 0.02,
        }
        for seed in (42, 43, 44):
            store.save(f"ppo-510300-s{seed}", b"fixture", {**manifest, "seed": seed})
        cfg = G.GridConfig(
            history_root=tmp_path / "h",
            models_root=store_path,
            out_root=tmp_path / "out",
            grid_id="diag",
            symbols=("510300",),
            algos=("ppo",),
            seeds=(42, 43, 44),
            eval_only=True,
        )
        return G.run_grid(
            cfg,
            train=G.train_run,
            scorer=self._scorer,
            provider=object(),
            printer=lambda *args, **kwargs: None,
        )

    def _scorer(self, cfg, job, provider, store=None):
        row = {
            "totalReturnPct": 1.0,
            "sharpe": self._sharpe,
            "trades": 10,
            "feesCny": 1.0,
        }
        return {
            job.algo: row,
            "ma_cross": dict(row),
            "buy_and_hold": {**row, "totalReturnPct": 0.0, "bars": 726},
            "excessVsBuyAndHoldPct": 1.0,
        }

    def test_ranking_is_marked_diagnostic_and_threshold_is_reported(self, tmp_path):
        summary = self._summary(tmp_path)
        ranked = summary["picks"]["byTestSharpe"]
        assert ranked["diagnosticOnly"] is True
        assert "ranking" in ranked
        assert "选择偏差" in ranked["reason"]
        assert "byValidation" in ranked["reason"]  # points at what selection uses

        noise = summary["noiseSharpeThreshold"]
        block = noise["bySymbol"]["510300"]
        assert block["trials"] == 3
        assert block["testBars"] == 726
        # Three trials on 726 bars put the noise floor near 0.55, so a 0.30 winner
        # is correctly reported as indistinguishable from noise.
        assert block["noiseSharpeThreshold"] > block["observedSharpe"]
        assert block["clearsNoiseThreshold"] is False
        assert noise["wholeGrid"]["trials"] == 3

    def test_summary_json_survives_strict_serialisation(self, tmp_path):
        """A non-positive winner Sharpe needs an infinite track record, so the
        artifact must carry null rather than Infinity — the latter is not valid
        strict JSON and breaks non-Python consumers."""
        self._summary(tmp_path, sharpe=0.0)
        raw = (tmp_path / "out" / "diag-summary.json").read_text(encoding="utf-8")
        assert "Infinity" not in raw
        block = json.loads(raw)["noiseSharpeThreshold"]["bySymbol"]["510300"]
        assert block["minTrackRecordLength"] is None
        # allow_nan=False is exactly what a strict parser enforces.
        json.dumps(json.loads(raw), allow_nan=False)

    def test_csv_carries_the_turnover_and_recipe_columns(self, tmp_path):
        self._summary(tmp_path)
        import csv

        with (tmp_path / "out" / "diag-summary.csv").open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert set(G.CSV_COLUMNS) == set(rows[0])
        for column in (
            "test_trades_per_year",
            "test_fees_pct_of_capital",
            "band_pct",
            "reward_mode",
            "selection_metric",
            "fold_scores",
        ):
            assert column in G.CSV_COLUMNS
        assert rows[0]["band_pct"] == "0.02"


class TestServingBandGate:
    """Acceptance (8): serving must replay the band the policy trained under."""

    def _manifest(self, **over):
        base = {
            "executionVersion": EXECUTION_VERSION,
            "algo": "ppo",
            "seed": 1,
            "featureSignature": feature_signature(),
            "publicationDate": "2024-12-31",
            "dataVersion": "d",
            "universeVersion": "u",
            "codeSha": "c",
            "trainStartDate": "2015-01-05",
            "trainEndDate": "2018-06-30",
        }
        base.update(over)
        return base

    def test_bundle_without_a_recorded_band_is_refused(self):
        strategy = RLStrategy(PPO)
        with pytest.raises(RLIncompatibleModel, match="bandPct"):
            strategy._verify_bundle(SimpleNamespace(manifest=self._manifest()))

    def test_bundle_with_a_band_passes_the_gate(self):
        RLStrategy(PPO)._verify_bundle(SimpleNamespace(manifest=self._manifest(bandPct=0.02)))

    def test_a_stale_feature_signature_is_still_refused(self):
        strategy = RLStrategy(PPO)
        stale = self._manifest(bandPct=0.02, featureSignature="deadbeefdeadbeef")
        with pytest.raises(RLIncompatibleModel, match="特征配方签名"):
            strategy._verify_bundle(SimpleNamespace(manifest=stale))


# --------------------------------------------------------------------------
# Heavy section: needs the [rl] extra.
# --------------------------------------------------------------------------

def _frame(rows=600, seed=3, drift=0.0, start="2015-01-05"):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0, 0.012, rows) + drift
    close = 100.0 * np.exp(np.cumsum(ret))
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=rows, freq="D"),
            "open": close,
            "high": close * 1.006,
            "low": close * 0.994,
            "close": close,
        }
    )


class TestRewardModes:
    """Acceptance (3): log_return unchanged, excess rewards being flat, penalty bites."""

    def _env(self, frame, **kw):
        pytest.importorskip("gymnasium")
        from quant_platform.rl.env import TradingEnv

        return TradingEnv(frame, **kw)

    def test_default_reward_is_the_portfolio_log_return(self):
        frame = _frame()
        env = self._env(frame, discrete=False, band_pct=0.0, min_trade_cny=0.0)
        env.reset(seed=0)
        total = 0.0
        done = False
        while not done:
            _, reward, done, _, _ = env.step(np.array([0.5], dtype=np.float32))
            total += reward
        equity = env._cash + env._shares * frame.close.iloc[-1]
        assert total == pytest.approx(np.log(equity / 100_000.0), rel=1e-12)

    def test_excess_reward_is_positive_when_flat_in_a_falling_market(self):
        # A drifting-down market still has up bars, so the claim is about the
        # window, not each bar: sitting flat must beat holding a decline.
        falling = _frame(seed=11, drift=-0.002)
        env = self._env(falling, discrete=False, band_pct=0.0, min_trade_cny=0.0,
                        reward_mode="excess")
        env.reset(seed=0)
        total = 0.0
        done = False
        while not done:
            _, reward, done, _, _ = env.step(np.array([0.0], dtype=np.float32))
            total += reward
        assert total > 0.0
        holding = float(np.log(falling.close.iloc[-1] / falling.close.iloc[env._first]))
        assert holding < 0.0  # the asset really did decline over the window
        assert total == pytest.approx(-holding, rel=1e-9)

    def test_excess_reward_matches_portfolio_minus_market(self):
        frame = _frame(seed=5)
        env = self._env(frame, discrete=False, band_pct=0.0, min_trade_cny=0.0,
                        reward_mode="excess")
        env.reset(seed=0)
        total = 0.0
        done = False
        while not done:
            _, reward, done, _, _ = env.step(np.array([0.0], dtype=np.float32))
            total += reward
        market = float(np.log(frame.close.iloc[-1] / frame.close.iloc[env._first]))
        assert total == pytest.approx(-market, rel=1e-9)

    def test_turnover_penalty_lowers_the_same_path(self):
        frame = _frame(seed=9)
        totals = []
        for penalty in (0.0, 2.0):
            env = self._env(frame, discrete=True, band_pct=0.0, min_trade_cny=0.0,
                            turnover_penalty=penalty)
            env.reset(seed=0)
            total = 0.0
            done = False
            flip = 0
            while not done:
                flip ^= 1
                _, reward, done, _, _ = env.step(2 if flip else 0)
                total += reward
            totals.append(total)
        assert totals[1] < totals[0]

    def test_dsr_reward_is_finite_and_bounded(self):
        frame = _frame(seed=13)
        env = self._env(frame, discrete=False, band_pct=0.0, min_trade_cny=0.0,
                        reward_mode="dsr")
        env.reset(seed=0)
        rewards = []
        done = False
        while not done:
            _, reward, done, _, _ = env.step(np.array([0.5], dtype=np.float32))
            rewards.append(reward)
            assert np.isfinite(reward)
        assert max(abs(value) for value in rewards) <= 10.0

    def test_unknown_reward_mode_is_refused(self):
        with pytest.raises(ValueError, match="reward_mode"):
            self._env(_frame(), reward_mode="sharpe")


class TestSampling:
    """Acceptance (5): random starts are reproducible and inside the frame."""

    def test_random_start_is_reproducible_and_bounded(self):
        pytest.importorskip("gymnasium")
        from quant_platform.rl.env import TradingEnv

        frame = _frame(rows=600)
        env = TradingEnv(frame, random_start=True, min_episode_bars=50)
        env.reset(seed=5)
        first = env._step_index
        env.reset(seed=5)
        assert env._step_index == first
        assert MIN_WARMUP <= first <= len(frame) - 1 - 50
        seen = set()
        for seed in range(12):
            env.reset(seed=seed)
            seen.add(env._step_index)
        assert len(seen) > 1  # a fixed start is exactly what CR-059 removed

    def test_random_start_needs_room_for_the_minimum_episode(self):
        pytest.importorskip("gymnasium")
        from quant_platform.rl.env import TradingEnv

        with pytest.raises(ValueError, match="随机起点"):
            TradingEnv(_frame(rows=MIN_WARMUP + 40), random_start=True, min_episode_bars=250)


class TestTurnoverGovernance:
    """Acceptance (4): a wider dead band actually removes fills."""

    def _fills(self, band):
        frame = _frame(rows=200)
        # Deviations of ~1500 CNY on 100k: above a 0.005 band (500), below 0.02 (2000).
        weights = pd.Series(
            [0.015 if i % 2 else 0.0 for i in range(len(frame))], index=frame.index
        )
        trades, _ = BacktestEngine(None, {})._simulate(
            "T", frame, weights, 100_000.0, TradingCosts(),
            "continuous_target_weight", band, 100.0,
        )
        return len(trades)

    def test_wider_band_removes_fills(self):
        assert self._fills(0.02) < self._fills(0.005)

    def test_the_default_band_is_the_wider_one(self):
        pytest.importorskip("gymnasium")
        import inspect

        from quant_platform.rl.env import TradingEnv

        assert inspect.signature(TradingEnv).parameters["band_pct"].default == 0.02


class TestFoldSelectionEndToEnd:
    """Acceptance (2): a real three-fold run records per-fold scores and selects on them."""

    class Provider:
        publication_context = {
            "publicationDate": "2024-12-31",
            "universeVersion": "cr059-test",
            "dataVersion": "b" * 64,
            "consistency": "synthetic_cr059",
        }

        def __init__(self, master):
            self._master = master

        def cache_revision(self):
            return "cr059-test"

        def history(self, symbol, start, end, adjust="qfq"):
            frame = self._master
            return frame[
                (frame.date >= pd.Timestamp(start)) & (frame.date <= pd.Timestamp(end))
            ].reset_index(drop=True)

    def test_three_folds_are_scored_and_the_median_selects(self, tmp_path):
        pytest.importorskip("stable_baselines3")
        pytest.importorskip("gymnasium")
        import torch

        torch.set_num_threads(1)
        master = _frame(rows=3660, seed=21, start="2015-01-01")
        provider = self.Provider(master)
        store = G.ModelStore(tmp_path / "models")
        cfg = G.GridConfig(
            history_root=tmp_path / "history",
            models_root=store.root,
            out_root=tmp_path / "out",
            grid_id="folds",
            symbols=("synth",),
            algos=("ppo",),
            seeds=(42,),
            train_start=date(2015, 1, 5),
            train_end=date(2018, 6, 30),
            test_start=date(2022, 1, 1),
            test_end=date(2024, 12, 31),
            timesteps=2048,
            eval_freq=1024,
            progress_every=2048,
            require_regimes=False,
        )
        assert len(cfg.val_folds) == 3  # the CR-059 default tiling
        lines: list[str] = []
        summary = G.run_grid(cfg, provider=provider, printer=lambda *a, **k: lines.append(a[0]))
        assert summary["failures"] == []
        assert summary["config"]["valFolds"] == [
            "2018-07-01..2019-09-30",
            "2019-10-01..2020-09-30",
            "2020-10-01..2021-12-31",
        ]

        manifest = G.ModelStore(store.root).load("ppo-synth-s42").manifest
        assert manifest["weightSelection"] == "validation-best"
        assert manifest["selectionMetric"] == "excessSharpe"
        assert manifest["bandPct"] == cfg.rebalance_band_pct
        assert len(manifest["valFolds"]) == 3
        fold_scores = manifest["foldScores"]
        assert len(fold_scores) == 3  # one score per fold, all recorded
        # The selected checkpoint is the best MEDIAN, not the best single fold.
        assert manifest["selectedFoldMedian"] == pytest.approx(S.median_fold_score(fold_scores))
        assert manifest["bestEvalReward"] == pytest.approx(manifest["selectedFoldMedian"])

        log_dir = store.root / "_trainlogs" / "ppo-synth-s42"
        assert (log_dir / "best_model.zip").exists()
        with np.load(log_dir / "evaluations.npz") as data:
            assert data["fold_scores"].shape[1] == 3
            assert len(data["timesteps"]) == len(data["results"])
        assert any("折 3 个" in line for line in lines)

    def test_median_beats_a_single_lucky_fold(self):
        """The selection statistic itself: one great fold cannot win on its own."""
        lucky = [5.0, -1.0, -1.0]  # best single fold, mediocre the rest
        steady = [0.6, 0.7, 0.5]
        assert S.median_fold_score(steady) > S.median_fold_score(lucky)


class TestUpdateAlignment:
    """Acceptance (6): the off-policy update count is aligned with the data volume."""

    def test_sac_updates_follow_train_freq_not_every_step(self, tmp_path):
        pytest.importorskip("stable_baselines3")
        pytest.importorskip("gymnasium")
        import torch

        from quant_platform.rl.train import train_run

        torch.set_num_threads(1)
        frame = _frame(rows=1500, seed=31)
        provider = SimpleNamespace(
            history=lambda symbol, start, end, adjust="qfq": frame,
            cache_revision=lambda: "cr059",
            publication_context={
                "publicationDate": "2020-12-31",
                "universeVersion": "cr059",
                "dataVersion": "b" * 64,
                "consistency": "synthetic_cr059",
            },
        )
        models_root = tmp_path / "models"
        steps = 400
        train_run(
            publication_root=tmp_path / "unused",
            models_root=models_root,
            run_id="sac-align",
            algo="sac",
            symbol="SYNTH",
            start=date(2015, 1, 5),
            end=date(2018, 6, 30),
            seed=42,
            total_timesteps=steps,
            eval_freq=0,
            progress_every=steps,
            provider=provider,
        )
        manifest = G.ModelStore(models_root).load("sac-align").manifest
        updates = manifest["gradientUpdates"]
        # train_freq=4 with learning_starts=100: about (steps - 100) / 4, not one
        # per step (which is what produced ~199,900 updates over ~1,078 transitions).
        assert updates <= (steps - 100) // 4 + 1
        assert updates < steps

    def test_spec_train_freq_is_recorded_and_slow(self):
        from quant_platform.rl.policies import RL_POLICIES

        for algo in ("sac", "td3", "dqn"):
            hyper = RL_POLICIES[algo].hyperparameters
            assert hyper["train_freq"] == 4
            assert hyper["gradient_steps"] == 1
            assert hyper["buffer_size"] <= 20_000

    def test_ddpg_is_kept_loadable_for_the_deployed_release(self):
        """Dropping ddpg would make store.validate_manifest reject live bundles."""
        from quant_platform.rl.policies import RESEARCH_ALGOS, RL_POLICIES

        assert "td3" in RL_POLICIES and "ddpg" in RL_POLICIES
        assert "td3" in RESEARCH_ALGOS and "ddpg" not in RESEARCH_ALGOS
        assert "dqn" in RESEARCH_ALGOS

    def test_spec_buffer_size_matches_the_pre_cr059_ddpg_default(self):
        """Guard the reason ddpg stays: its spec must not drift under live weights."""
        from quant_platform.rl.policies import RL_POLICIES

        assert RL_POLICIES["ddpg"].hyperparameters["buffer_size"] == 200_000


class TestResumeEta:
    """CR-058 defect fixed here: a resumed grid printed a garbage near-zero ETA.

    Skipped runs cost no time, so counting them in the extrapolation denominator
    collapsed the estimate while real training was still ahead.
    """

    def test_skipped_runs_do_not_dilute_the_estimate(self, tmp_path):
        import time

        store = G.ModelStore(tmp_path / "models")
        manifest = {
            "executionVersion": EXECUTION_VERSION,
            "algo": "ppo",
            "seed": 42,
            "featureSignature": feature_signature(),
            "publicationDate": "2024-12-31",
            "dataVersion": "d",
            "universeVersion": "u",
            "codeSha": "c",
            "trainStartDate": "2015-01-05",
            "trainEndDate": "2018-06-30",
            "bandPct": 0.02,
        }
        store.save("ppo-510300-s42", b"fixture", manifest)

        def slow_train(**kw):
            time.sleep(1.1)  # so the measured wallSeconds formats as >= 1 second
            store.save(kw["run_id"], b"fixture", {**manifest, "seed": kw["seed"]})
            return store.root / kw["run_id"]

        cfg = G.GridConfig(
            history_root=tmp_path / "h",
            models_root=store.root,
            out_root=tmp_path / "out",
            grid_id="eta",
            symbols=("510300",),
            algos=("ppo",),
            seeds=(42, 43, 44),
        )
        lines: list[str] = []
        summary = G.run_grid(
            cfg,
            train=slow_train,
            scorer=TestSummaryContracts._scorer,
            provider=object(),
            printer=lambda *args, **kwargs: lines.append(args[0]),
        )
        assert summary["totals"]["skippedExisting"] == 1
        # Record lines are the ones carrying the measured wall time; the header
        # line also starts with "[grid ".
        grid_lines = [line for line in lines if "run用时" in line]
        assert len(grid_lines) == 3
        skipped, trained = grid_lines[0], grid_lines[1]
        # Job order is symbol-major then seed, so these are the skipped s42 and
        # the freshly trained s43. (A skipped run still reports status "ok".)
        assert "ppo-510300-s42" in skipped
        assert "ppo-510300-s43" in trained
        # The skipped record has no trained sample behind it yet: say n/a rather
        # than the bogus tiny number this used to print.
        assert "n/a" in skipped
        assert "网格ETA 0:00:00" not in skipped
        # Once a run has actually trained, the estimate is real and non-zero.
        assert "n/a" not in trained
        assert "网格ETA 0:00:01" in trained


class TestFoldWindowsFromCli:
    """Acceptance (1) at the CLI edge: the flags reach the gate unchanged."""

    def test_val_folds_flag_reaches_the_config(self, tmp_path):
        cfg = G.config_from_args(
            G.build_parser().parse_args(
                [
                    "--history-root", str(tmp_path / "h"),
                    "--models-root", str(tmp_path / "m"),
                    "--val-folds", "2018-07-01:2019-09-30", "2019-10-01:2020-09-30",
                    "--val-start", "2018-07-01", "--val-end", "2020-09-30",
                ]
            )
        )
        assert tuple(cfg.val_folds) == (
            (date(2018, 7, 1), date(2019, 9, 30)),
            (date(2019, 10, 1), date(2020, 9, 30)),
        )
        cfg.validate()

    def test_mismatched_fold_bounds_are_refused(self, tmp_path):
        cfg = G.config_from_args(
            G.build_parser().parse_args(
                ["--history-root", str(tmp_path / "h"), "--models-root", str(tmp_path / "m")]
            )
        )
        cfg.val_end = cfg.val_end - timedelta(days=1)
        with pytest.raises(ValueError, match="外沿"):
            cfg.validate()

    def test_default_train_window_is_the_cr059_one(self, tmp_path):
        cfg = G.config_from_args(
            G.build_parser().parse_args(
                ["--history-root", str(tmp_path / "h"), "--models-root", str(tmp_path / "m")]
            )
        )
        cfg.validate()
        assert cfg.train_end == date(2018, 6, 30)
        assert cfg.timesteps == 500_000
        assert cfg.rebalance_band_pct == 0.02
        assert cfg.selection_metric == "excessSharpe"
        assert cfg.reward_mode == "log_return"