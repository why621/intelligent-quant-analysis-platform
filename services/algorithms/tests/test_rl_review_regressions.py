"""CR045 regression cases use synthetic prices, never profitability evidence."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.backtesting.execution import EXECUTION_VERSION
from quant_platform.models import BacktestRequest, TradingCosts
from quant_platform.rl.errors import RLIncompatibleModel, RLInsufficientHistory
from quant_platform.rl.features import feature_signature
from quant_platform.rl.policies import RL_POLICIES, RLStrategy
from quant_platform.rl.store import ModelStore


def prices(n=45):
    # Gaps between dates model a sequence of observed tradable bars, not fills.
    close = 100 + 2 * np.sin(np.arange(n))
    return pd.DataFrame({
        "date": pd.bdate_range("2025-01-02", periods=n), "open": close * 1.01,
        "high": close * 1.02, "low": close * .98, "close": close,
    })


def manifest(algo="ppo"):
    return {
        "algo": algo, "seed": 42, "featureSignature": feature_signature(),
        "executionVersion": EXECUTION_VERSION, "publicationDate": "2025-06-30",
        "dataVersion": "data-a", "universeVersion": "universe-a", "codeSha": "code-a",
        "trainStartDate": "2024-01-01", "trainEndDate": "2024-12-31",
    }


class RecordingPolicy:
    def __init__(self, discrete=False):
        self.discrete = discrete
        self.observed = []

    def predict(self, obs, deterministic=True):
        self.observed.append(float(obs[-1]))
        i = len(self.observed) - 1
        if self.discrete:
            action = [1, 1, 0, 0, 1, 0][i % 6]
        elif i == 0:
            action = .004
        else:
            # Include decisions contingent on the actual account, including
            # the small first order which the rebalance band can suppress.
            action = .8 if obs[-1] < .2 else 0.
        return np.array([action]), None


@pytest.mark.parametrize("algo", sorted(RL_POLICIES))
@pytest.mark.parametrize("capital,costs,band,minimum", [
    (100000., TradingCosts(), .005, 100.),
    (1000., TradingCosts(0., 0., 0.), 0., 0.),
    (60000., TradingCosts(.2, .3, .4), .01, 700.),
])
def test_model_observes_actual_executed_account(algo, capital, costs, band, minimum):
    frame = prices()
    policy = RecordingPolicy(RL_POLICIES[algo].discrete)
    strategy = RLStrategy(RL_POLICIES[algo], model=policy,
                          bundle=SimpleNamespace(manifest=manifest(algo)),
                          rebalance_band_pct=band, min_trade_cny=minimum)
    # Keep real engine request dispatch, without loading SB3 for this unit case.
    strategy.create_for_request = lambda parameters: strategy
    strategy.generate_signals = lambda *a: pytest.fail("must use actual-account callback")
    provider = SimpleNamespace(history=lambda *a: frame)
    result = BacktestEngine(provider, {algo: strategy}).run(BacktestRequest(
        symbols=("TEST",), strategy_id=algo, start_date=frame.date.iloc[0].date(),
        end_date=frame.date.iloc[-1].date(), initial_capital_cny=capital, trading_costs=costs,
        parameters={"modelRef": "case-a"},
    ))
    assert len(policy.observed) == len(frame) - 21
    for bar, observed in enumerate(policy.observed, start=20):
        cash, shares = capital, 0.
        for trade in result.trades:
            if trade.trade_date > frame.date.iloc[bar].date():
                continue
            if trade.side == "buy":
                cash -= trade.amount_cny + trade.fee_cny
                shares += trade.quantity
            else:
                cash += trade.amount_cny - trade.fee_cny
                shares -= trade.quantity
        equity = cash + shares * frame.close.iloc[bar]
        assert cash >= -1e-8
        assert observed == pytest.approx(shares * frame.close.iloc[bar] / equity, abs=1e-7)
    if algo != "dqn" and capital == 100000:
        assert policy.observed[1] == 0.  # Initial 400 CNY order must be skipped.
    assert all(t.trade_date > frame.date.iloc[20].date() for t in result.trades)


@pytest.mark.parametrize("n", [0, 1, 20, 21])
def test_short_observed_history_is_typed_error(n):
    strategy = RLStrategy(RL_POLICIES["ppo"], model=RecordingPolicy(),
                          bundle=SimpleNamespace(manifest=manifest()))
    with pytest.raises(RLInsufficientHistory, match="22"):
        strategy.prepare_inference(prices(n), {})
    strategy.create_for_request = lambda parameters: strategy
    provider = SimpleNamespace(history=lambda *a: prices(n))
    request = BacktestRequest(
        symbols=("TEST",), strategy_id="ppo", parameters={"modelRef": "short"},
        start_date=pd.Timestamp("2025-01-01").date(),
        end_date=pd.Timestamp("2025-06-30").date(),
    )
    with pytest.raises(RLInsufficientHistory):
        BacktestEngine(provider, {"ppo": strategy}).run(request)


def test_minimum_history_and_causality():
    frame = prices(22)
    policy = RecordingPolicy()
    strategy = RLStrategy(RL_POLICIES["ppo"], model=policy,
                          bundle=SimpleNamespace(manifest=manifest()))
    first = strategy.prepare_inference(frame, {})(20, .3)
    frame.loc[21, ["open", "high", "low", "close"]] *= 4
    second = strategy.prepare_inference(frame, {})(20, .3)
    assert first == .004
    # Compare observations with a model that returns a function of features.
    strategy._model = SimpleNamespace(predict=lambda obs, **kw: ([float(obs[0])], None))
    changed = strategy.prepare_inference(frame, {})(20, .3)
    original = strategy.prepare_inference(prices(22), {})(20, .3)
    assert changed == original
    assert np.isfinite(second)


@pytest.mark.parametrize("field,value", [
    ("trainEndDate", ""), ("trainEndDate", "2024-06-30"),
    ("trainEndDate", "2024-02-30"), ("trainStartDate", "2026-01-01"),
    ("dataVersion", "data-b"), ("universeVersion", "universe-b"),
    ("publicationDate", "2025-07-01"), ("codeSha", "code-b"),
    ("seed", 43), ("seed", True), ("runId", "other-run"),
    ("modelSizeBytes", True), ("executionVersion", "legacy"),
    ("schemaVersion", 1), ("featureSignature", "changed"),
])
def test_manifest_edit_fails_before_inference(tmp_path, field, value):
    store = ModelStore(tmp_path)
    store.save("test-run", b"fixture", manifest())
    path = tmp_path / "test-run/manifest.json"
    doc = json.loads(path.read_text())
    doc[field] = value
    path.write_text(json.dumps(doc))
    with pytest.raises(RLIncompatibleModel):
        store.load("test-run")


@pytest.mark.parametrize("field", ["trainEndDate", "bundleHash", "executionVersion", "dataVersion"])
def test_missing_binding_is_rejected(tmp_path, field):
    store = ModelStore(tmp_path)
    store.save("test-run", b"fixture", manifest())
    path = tmp_path / "test-run/manifest.json"
    doc = json.loads(path.read_text())
    del doc[field]
    path.write_text(json.dumps(doc))
    with pytest.raises(RLIncompatibleModel):
        store.load("test-run")


def test_valid_roundtrip_hash_binds_metadata_and_old_execution_is_refused(tmp_path, monkeypatch):
    store = ModelStore(tmp_path)
    store.save("test-run", b"fixture", manifest())
    original = store.load("test-run")
    store.save("test-run", b"fixture", {**manifest(), "seed": 43})
    updated = store.load("test-run")
    assert original.manifest["contentHash"] == updated.manifest["contentHash"]
    assert original.manifest["bundleHash"] != updated.manifest["bundleHash"]
    store.save("old-run", b"fixture", {**manifest(), "executionVersion": "old"})
    monkeypatch.setattr(RLStrategy, "_load_model", lambda s: pytest.fail("must reject first"))
    with pytest.raises(RLIncompatibleModel, match="重新训练"):
        RLStrategy(RL_POLICIES["ppo"], store=store).create_for_request({"modelRef": "old-run"})


@pytest.mark.parametrize("value", [None, "", "2025-02-30", "20230101"])
def test_invalid_training_dates_cannot_disable_guard(value):
    strategy = RLStrategy(RL_POLICIES["ppo"], model=RecordingPolicy(),
                          bundle=SimpleNamespace(manifest={**manifest(), "trainEndDate": value}))
    with pytest.raises(RLIncompatibleModel):
        strategy.generate_signals(prices(), {})
