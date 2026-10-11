"""CR065 joint-account/causality/bundle regressions; ML smoke is separately marked."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import PORTFOLIO_EXECUTION_VERSION, rebalance_portfolio
from quant_platform.rl.errors import RLInsufficientHistory
from quant_platform.rl.features import MIN_WARMUP
from quant_platform.rl.portfolio_env import PortfolioEpisode
from quant_platform.rl.portfolio_features import (
    ACTION_SIZE,
    ENVIRONMENT_VERSION,
    OBSERVATION_SIZE,
    SLOT_SIZE,
    action_weights,
    encode_observation,
    observation_signature,
    prepare_panel,
)
from quant_platform.rl.portfolio_policy import (
    PortfolioBundle,
    costs_metadata,
    load_portfolio_bundle,
    prepare_portfolio_policy,
    research_backtest,
    save_portfolio_bundle,
    validate_manifest,
    validate_splits,
)
from quant_platform.rl.portfolio_train import train_portfolio, training_frames


def frames(count=3, bars=300, flat=False):
    result = {}
    dates = pd.bdate_range("2024-01-02", periods=bars)
    for asset in range(count):
        t = np.arange(bars)
        close = (
            np.full(bars, 10.0) if flat else 10 + asset + 0.02 * t + 0.2 * np.sin(t * 0.17 + asset)
        )
        open_ = close if flat else close - 0.05
        result[f"A{asset}"] = pd.DataFrame(
            {
                "date": dates,
                "open": open_,
                "high": close + 0.1,
                "low": open_ - 0.1,
                "close": close,
            }
        )
    return result


ZERO_COSTS = TradingCosts(0, 0, 0)


def episode(source=None, **kwargs):
    source = frames() if source is None else source
    return PortfolioEpisode(
        source,
        asset_types=dict.fromkeys(source, "etf"),
        trading_costs=kwargs.pop("trading_costs", ZERO_COSTS),
        **kwargs,
    )


def action(*scores, cash=0):
    result = np.zeros(ACTION_SIZE)
    result[: len(scores)] = scores
    result[-1] = cash
    return result


def manifest(source):
    dates = source["A0"]["date"]
    train = {symbol: frame.iloc[:191].copy() for symbol, frame in source.items()}
    return {
        "schemaVersion": 1,
        "runId": "test-joint",
        "algo": "ppo",
        "portfolioMode": "joint_portfolio",
        "environmentVersion": ENVIRONMENT_VERSION,
        "executionVersion": PORTFOLIO_EXECUTION_VERSION,
        "observationSignature": observation_signature(),
        "observationShape": [OBSERVATION_SIZE],
        "actionShape": [ACTION_SIZE],
        "minAssets": 2,
        "maxAssets": 10,
        "trainingUniverse": list(source),
        "assetTypes": dict.fromkeys(source, "etf"),
        "dataHashes": dict(prepare_panel(train).data_hashes),
        "splits": {
            "trainStartDate": str(dates.iloc[0].date()),
            "trainEndDate": str(dates.iloc[190].date()),
            "valStartDate": str(dates.iloc[191].date()),
            "valEndDate": str(dates.iloc[210].date()),
            "testStartDate": str(dates.iloc[211].date()),
            "testEndDate": str(dates.iloc[-1].date()),
        },
        "tradingCosts": costs_metadata(ZERO_COSTS),
        "generalization": "unverified",
        "performanceStatus": "unproven",
        "releaseEligible": False,
    }


class ScriptedModel:
    """Explicit test double; never used as evidence of actual model training."""

    observation_space = SimpleNamespace(shape=(OBSERVATION_SIZE,))
    action_space = SimpleNamespace(shape=(ACTION_SIZE,))

    def predict(self, obs, deterministic=True):
        assert deterministic
        # Alternate from cash into the first slot, then switch to the second.
        current_weight = obs.reshape(-1)[SLOT_SIZE - 2]
        return (action(1, 0) if current_weight < 0.5 else action(0, 1)), None

    def save(self, path):
        Path(path).write_bytes(b"test-double-not-trained-model")


@pytest.mark.parametrize("count", [2, 3, 10])
def test_joint_observation_and_action_hard_mask(count):
    obs = encode_observation(np.zeros((count, 14)), np.ones(count), np.full(count, 10), 100)
    slots = obs[:-1].reshape(10, SLOT_SIZE)
    assert obs.shape == (OBSERVATION_SIZE,)
    assert np.all(slots[:count, -1] == 1)
    assert np.all(slots[count:] == 0)
    assert slots[:, -2].sum() + obs[-1] == pytest.approx(1)
    weights = action_weights(np.ones(11), count)
    assert weights.sum() == pytest.approx(1)
    assert np.all(weights[count:10] == 0)
    assert np.count_nonzero(weights[:10]) == count


@pytest.mark.parametrize("bad", [np.full(11, np.nan), np.full(11, -1), np.ones(10), np.full(11, 2)])
def test_invalid_joint_action_rejected(bad):
    with pytest.raises(ValueError):
        action_weights(bad, 2)


def test_zero_action_means_cash_not_equal_weight():
    weights = action_weights(np.zeros(11), 3)
    assert weights[-1] == 1
    assert np.all(weights[:-1] == 0)


def test_missing_asset_date_is_not_filled_or_silently_removed():
    source = frames(2)
    source["A1"] = source["A1"].drop(index=200)
    with pytest.raises(ValueError, match="dates differ"):
        prepare_panel(source)


def test_future_price_changes_do_not_change_earlier_joint_features():
    source = frames(2)
    original = prepare_panel(source)
    altered = {symbol: frame.copy() for symbol, frame in source.items()}
    altered["A1"].loc[230:, ["open", "high", "low", "close"]] *= 2
    changed = prepare_panel(altered)
    np.testing.assert_array_equal(original.features[:230], changed.features[:230])
    assert original.data_hashes["A1"] != changed.data_hashes["A1"]


def test_shared_cash_transfers_all_capital_between_assets():
    env = episode(
        frames(2, flat=True),
        initial_capital=1000,
        random_subsets=False,
        random_start=False,
        episode_bars=2,
    )
    env.reset()
    _, reward, done, _, first = env.step(action(1, 0))
    assert not done and reward == pytest.approx(0)
    assert first["quantities"] == pytest.approx([100, 0])
    _, reward, done, _, second = env.step(action(0, 1))
    assert done and reward == pytest.approx(0)
    assert second["quantities"] == pytest.approx([0, 100])
    assert [(fill["symbol"], fill["side"]) for fill in second["fills"]] == [
        ("A0", "sell"),
        ("A1", "buy"),
    ]
    assert second["equity"] == 1000
    with pytest.raises(RuntimeError, match="reset"):
        env.step(action(1, 0))


def test_environment_matches_public_broker_each_day_including_costs():
    source = frames(3)
    costs = TradingCosts(0.2, 0.05, 0.1, "asset_date")
    env = episode(
        source,
        trading_costs=costs,
        initial_capital=1000,
        random_subsets=False,
        random_start=False,
        episode_bars=3,
    )
    env.reset()
    cash, quantities = 1000, np.zeros(3)
    fees, slippage = 0.0, 0.0
    for vector in (action(1, 0, 0), action(0, 0.4, 0.6), action(0.3, 0.2, 0.1, cash=0.4)):
        bar = env.bar + 1
        expected = rebalance_portfolio(
            cash=cash,
            quantities=quantities,
            target_weights=vector[:3],
            prices=env.panel.opens[bar],
            symbols=env.symbols,
            asset_types=["etf"] * 3,
            trade_date=env.panel.dates[bar].date(),
            costs=costs,
        )
        _, _, _, _, info = env.step(vector)
        cash, quantities = expected.cash, expected.quantities
        fees += sum(fill.fee_cny for fill in expected.fills)
        slippage += sum(fill.slippage_cny for fill in expected.fills)
        assert env.cash == pytest.approx(cash)
        np.testing.assert_allclose(env.quantities, quantities)
        assert info["equity"] == pytest.approx(cash + quantities @ env.panel.closes[bar])
        assert info["cumulativeFees"] == pytest.approx(fees)
        assert info["cumulativeSlippage"] == pytest.approx(slippage)


def test_action_executes_next_open_and_rewards_next_close():
    source = frames(2, flat=True)
    source["A0"].loc[141, ["open", "high", "low", "close"]] = [20, 31, 19, 30]
    env = episode(
        source, initial_capital=1000, episode_bars=1, random_start=False, random_subsets=False
    )
    env.reset()
    _, reward, _, _, info = env.step(action(1, 0))
    assert info["quantities"] == pytest.approx([50, 0])
    assert info["equity"] == pytest.approx(1500)
    assert reward == pytest.approx(np.log(1.5))


def test_symbol_reordering_does_not_change_shared_execution():
    source = frames(3)
    left = episode(source, random_start=False, episode_bars=2)
    right = episode(source, random_start=False, episode_bars=2)
    left.reset(options={"symbols": ["A0", "A1", "A2"]})
    right.reset(options={"symbols": ["A2", "A1", "A0"]})
    for weights in ([0.6, 0.3, 0.1], [0.1, 0.5, 0.4]):
        _, _, _, _, a = left.step(action(*weights))
        _, _, _, _, b = right.step(action(*reversed(weights)))
        assert a["equity"] == pytest.approx(b["equity"])
        assert dict(zip(a["symbols"], a["quantities"], strict=True)) == pytest.approx(
            dict(zip(b["symbols"], b["quantities"], strict=True))
        )


def test_sampling_changes_joint_subsets_slot_order_and_training_windows_reproducibly():
    env = episode(frames(12), episode_bars=32)
    sizes, pools, starts = set(), set(), set()
    for index in range(60):
        obs, info = env.reset(seed=42 if index == 0 else None)
        sizes.add(len(env.symbols))
        pools.add(env.symbols)
        starts.add(env.bar)
        assert MIN_WARMUP <= env.bar < env.end_bar < 300
        assert len(info["symbols"]) >= 2
        assert np.isfinite(obs).all()
    assert 2 in sizes and 10 in sizes
    assert len(pools) > 20 and len(starts) > 20
    first = env.sample_log[0]
    _, repeated = env.reset(seed=42)
    assert repeated["episode"] == first


def test_time_split_happens_before_features_and_sampling():
    source = frames(3)
    config = manifest(source)
    selected = training_frames(source, config["splits"])
    expected = prepare_panel(selected)
    changed = {symbol: frame.copy() for symbol, frame in source.items()}
    changed["A1"].loc[191:, ["open", "high", "low", "close"]] *= 3
    actual = prepare_panel(training_frames(changed, config["splits"]))
    assert len(actual.dates) == 191
    assert actual.data_hashes == expected.data_hashes
    np.testing.assert_array_equal(actual.features, expected.features)


@pytest.mark.parametrize(
    "splits",
    [
        {
            "trainStartDate": "2024-01-01",
            "trainEndDate": "2024-12-31",
            "valStartDate": "2024-05-01",
        },
        {
            "trainStartDate": "2024-01-01",
            "trainEndDate": "2024-12-31",
            "valStartDate": "2024-12-31",
            "valEndDate": "2025-01-31",
        },
    ],
)
def test_incomplete_or_overlapping_splits_are_rejected(splits):
    with pytest.raises(ValueError):
        validate_splits(splits)


def test_bundle_integrity_and_legacy_isolation_before_model_loading(tmp_path):
    source = frames()
    config = manifest(source)
    path = save_portfolio_bundle(ScriptedModel(), tmp_path, config)
    loaded = load_portfolio_bundle(path, model_loader=lambda algo, path: ScriptedModel())
    assert loaded.manifest["portfolioMode"] == "joint_portfolio"
    with pytest.raises(FileExistsError):
        save_portfolio_bundle(ScriptedModel(), tmp_path, config)
    meta_path = path / "manifest.json"
    edited = json.loads(meta_path.read_text())
    edited["tradingCosts"]["commissionPct"] = 0.5
    meta_path.write_text(json.dumps(edited))
    with pytest.raises(ValueError, match="integrity"):
        load_portfolio_bundle(path, model_loader=lambda *_: pytest.fail("must fail before ML load"))
    with pytest.raises(ValueError, match="legacy"):
        validate_manifest({"algo": "ppo", "featureSignature": "old-single-asset"})


def test_bundle_rejects_incompatible_network_shape(tmp_path):
    path = save_portfolio_bundle(ScriptedModel(), tmp_path, manifest(frames()))
    with pytest.raises(ValueError, match="dimensions"):
        load_portfolio_bundle(
            path,
            model_loader=lambda *_: SimpleNamespace(
                action_space=SimpleNamespace(shape=(1,)),
                observation_space=SimpleNamespace(shape=(15,)),
            ),
        )


def test_joint_inference_rejects_in_sample_unseen_assets_and_cost_mismatch(tmp_path):
    source = frames()
    bundle = PortfolioBundle(manifest(source), ScriptedModel(), tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        prepare_portfolio_policy(bundle, source, evaluation_start=date(2024, 1, 2))
    unseen = {"A0": source["A0"], "UNSEEN": source["A1"]}
    with pytest.raises(ValueError, match="unseen"):
        prepare_portfolio_policy(bundle, unseen, evaluation_start=date(2025, 1, 1))
    with pytest.raises(ValueError, match="costs"):
        prepare_portfolio_policy(
            bundle, source, evaluation_start=date(2025, 1, 1), trading_costs=TradingCosts()
        )


def test_serving_canonicalizes_symbols_and_requires_real_warmup(tmp_path):
    source = frames()
    bundle = PortfolioBundle(manifest(source), ScriptedModel(), tmp_path)
    start = source["A0"]["date"].iloc[220].date()
    left = prepare_portfolio_policy(bundle, source, evaluation_start=start)
    right = prepare_portfolio_policy(
        bundle, dict(reversed(list(source.items()))), evaluation_start=start
    )
    assert left.symbols == right.symbols
    np.testing.assert_array_equal(
        left.target_weights(220, 1000, np.zeros(3)), right.target_weights(220, 1000, np.zeros(3))
    )
    truncated = {symbol: frame.iloc[200:].copy() for symbol, frame in source.items()}
    with pytest.raises(RLInsufficientHistory):
        prepare_portfolio_policy(bundle, truncated, evaluation_start=start)
    too_little_warmup = {symbol: frame.iloc[100:].copy() for symbol, frame in source.items()}
    with pytest.raises(ValueError, match="warm-up"):
        prepare_portfolio_policy(bundle, too_little_warmup, evaluation_start=start)


def test_research_replay_uses_shared_ledger_and_snapshot_metadata(tmp_path):
    source = frames(2, flat=True)
    bundle = PortfolioBundle(manifest(source), ScriptedModel(), tmp_path)
    result = research_backtest(
        bundle, source, evaluation_start=source["A0"]["date"].iloc[296].date(), initial_capital=1000
    )
    assert len(result["accountCurve"]) == 4
    assert result["accountCurve"][1]["quantities"] == pytest.approx([100, 0])
    assert result["accountCurve"][2]["quantities"] == pytest.approx([0, 100])
    assert result["accountCurve"][-1]["equity"] == pytest.approx(1000)
    assert result["performanceStatus"] == "unproven"


@pytest.mark.parametrize(
    "extra", [{"algo": "dqn"}, {"total_timesteps": 10_001}, {"max_seconds": 601}]
)
def test_training_budget_and_algorithm_are_checked_without_ml(tmp_path, extra):
    source = frames(2)
    with pytest.raises(ValueError):
        train_portfolio(
            source,
            asset_types=dict.fromkeys(source, "etf"),
            trading_costs=ZERO_COSTS,
            splits=manifest(source)["splits"],
            output_root=tmp_path,
            run_id="bounded",
            **extra,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.rl
@pytest.mark.parametrize("algo", ["ppo", "sac", "td3"])
def test_optional_actual_joint_learn_save_load_predict(tmp_path, algo):
    pytest.importorskip("gymnasium")
    pytest.importorskip("stable_baselines3")
    source = frames(3)
    path = train_portfolio(
        source,
        asset_types=dict.fromkeys(source, "etf"),
        trading_costs=ZERO_COSTS,
        splits=manifest(source)["splits"],
        output_root=tmp_path,
        run_id=f"smoke-{algo}",
        algo=algo,
        total_timesteps=128,
        max_seconds=90,
        episode_bars=16,
    )
    metadata = json.loads((path / "manifest.json").read_text())
    verification = json.loads((path / "smoke-verification.json").read_text())
    assert metadata["actualTimesteps"] >= 128 and metadata["optimizerUpdates"] > 0
    assert verification["loaded"] and verification["jointActionDimension"] == 11
    assert len(verification["simultaneousAssets"]) >= 2
    assert metadata["releaseEligible"] is False
