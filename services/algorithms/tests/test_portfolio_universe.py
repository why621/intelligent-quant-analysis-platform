"""CR069 offline gates and account invariants; policies/evidence here are test doubles."""

import hashlib
import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from test_portfolio_rl import ScriptedModel, frames, manifest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.calendar import sessions
from quant_platform.models import BacktestRequest, TradingCosts
from quant_platform.rl.errors import RLInsufficientHistory
from quant_platform.rl.portfolio_evaluation import evaluate_portfolio
from quant_platform.rl.portfolio_features import prepare_panel
from quant_platform.rl.portfolio_policy import PortfolioBundle
from quant_platform.rl.portfolio_release import validated_serving_scope
from quant_platform.rl.portfolio_strategy import JointPortfolioStrategy


def released(monkeypatch, tmp_path):
    source = frames(12)
    dates = pd.to_datetime(sessions(date(2025, 1, 2), date(2026, 6, 30))[:300])
    for frame in source.values():
        frame["date"] = dates
    types = {s: "stock" if s in {"A0", "A10"} else "etf" for s in source}
    metadata = manifest({s: source[s] for s in list(source)[:10]})
    metadata["assetTypes"] = {s: types[s] for s in metadata["trainingUniverse"]}
    metadata.update(
        purpose="formal_candidate", actualTimesteps=65536, optimizerUpdates=100, bundleHash="a" * 64
    )
    bundle = PortfolioBundle(metadata, ScriptedModel(), tmp_path)
    monkeypatch.setattr(
        "quant_platform.rl.portfolio_strategy.load_portfolio_bundle", lambda _: bundle
    )
    base = json.dumps(dict(bundleHash="a" * 64, ledgerPassed=True, simultaneousAssets=10)).encode()
    (tmp_path / "evaluation.json").write_bytes(base)
    release = dict(
        bundleHash="a" * 64,
        evaluationSha256=hashlib.sha256(base).hexdigest(),
        targetUniverseVersion="u",
        scopeDataVersion="d",
        assetScope="published_universe",
        costPolicy="request_configurable",
        supportedAssetTypes=types,
    )
    evidence = dict(
        evidenceKind="real_market_cross_asset_replay",
        bundleHash="a" * 64,
        targetUniverseVersion="u",
        scopeDataVersion="d",
        supportedAssetTypes=types,
        coverageSymbols=list(source),
        heldOutSymbols=["A10", "A11"],
        ledgerPassed=True,
        permutationPassed=True,
        mixedAssetTypesPassed=True,
        costAdaptationPassed=True,
        cashReservePassed=True,
        replays=[
            dict(
                symbols=group,
                startDate=dates[211].date().isoformat(),
                endDate=dates[-1].date().isoformat(),
                ledgerPassed=True,
                permutationPassed=True,
            )
            for group in [list(source)[:10], ["A10", "A11"]]
        ],
    )
    write_evidence(tmp_path, release, evidence)

    class Provider:
        start = dates[0].date()
        publication_context = {"universeVersion": "u"}

        def list_assets(self, **kwargs):
            return [SimpleNamespace(symbol=s, asset_type=kind) for s, kind in types.items()]

        def history(self, symbol, start, end, adjust):
            frame = source[symbol]
            return frame[(frame.date >= pd.Timestamp(start)) & (frame.date <= pd.Timestamp(end))]

    return source, bundle, release, evidence, Provider()


def write_evidence(path, release, evidence):
    raw = json.dumps(evidence).encode()
    (path / "cross-asset-evaluation.json").write_bytes(raw)
    release["crossAssetEvidenceSha256"] = hashlib.sha256(raw).hexdigest()


def request(source, **changes):
    result = BacktestRequest(
        ("A10", "A11"),
        "portfolio_ppo",
        source["A0"].date.iloc[211].date(),
        source["A0"].date.iloc[-1].date(),
        parameters={"modelRef": "test-joint"},
        trading_costs=TradingCosts(0.1, 0.05, 0.02, "asset_date"),
        portfolio_mode="shared_account",
        cash_pct=25,
    )
    return replace(result, **changes)


def test_catalog_scope_is_separate_from_training_and_uses_requested_costs(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    context = strategy.model_context()
    assert len(context["trainingSymbols"]) == 10 and len(context["symbols"]) == 12
    assert context["crossAssetValidationStatus"] == "execution_validated"
    assert context["performanceStatus"] == "unproven"
    assert context["costPolicy"] == "request_configurable"
    assert "requiredTradingCosts" not in context
    payload = dict(
        symbols=["A10", "A11"],
        portfolioMode="shared_account",
        cashPct=25,
        startDate=request(source).start_date.isoformat(),
    )
    strategy.validate_web_request(payload, provider)
    engine = BacktestEngine(provider, {"portfolio_ppo": strategy})
    result, weights = strategy.run_joint(engine, request(source), with_target=True)
    assert result.cost_summary["totalTradingCostCny"] > 0
    assert sum(weights.values()) <= 0.75 + 1e-9
    assert result.assumptions["costsDifferFromTraining"] == "true"
    assert any(t.stamp_duty_cny > 0 for t in result.trades if t.symbol == "A10")
    assert all(t.stamp_duty_cny == 0 for t in result.trades if t.symbol == "A11")
    reverse = engine.run(replace(request(source), symbols=("A11", "A10")))
    assert reverse.account_curve == result.account_curve
    assert all(p["cashCny"] >= 0 for p in result.account_curve)
    assert all(
        sum(x["weightPct"] for x in p["positions"]) <= 100 + 1e-8 for p in result.account_curve
    )


@pytest.mark.parametrize(
    "change",
    [
        {"bundleHash": "b" * 64},
        {"scopeDataVersion": "wrong"},
        {"coverageSymbols": ["A0", "A1"]},
        {"heldOutSymbols": ["A0", "A1"]},
        {"replays": []},
        {"cashReservePassed": False},
        {"costAdaptationPassed": False},
        {"mixedAssetTypesPassed": False},
        {"ledgerPassed": False},
    ],
)
def test_new_scope_requires_matching_complete_real_replay_gate(monkeypatch, tmp_path, change):
    _, bundle, release, evidence, _ = released(monkeypatch, tmp_path)
    write_evidence(tmp_path, release, {**evidence, **change})
    with pytest.raises(ValueError):
        validated_serving_scope(tmp_path, bundle.manifest, release)


def test_cross_scope_hash_and_mixed_training_gate(monkeypatch, tmp_path):
    _, bundle, release, _, _ = released(monkeypatch, tmp_path)
    release["crossAssetEvidenceSha256"] = "f" * 64
    with pytest.raises(ValueError, match="evidence"):
        validated_serving_scope(tmp_path, bundle.manifest, release)
    bundle.manifest["assetTypes"] = dict.fromkeys(bundle.manifest["trainingUniverse"], "stock")
    with pytest.raises(ValueError, match="mixed training"):
        validated_serving_scope(tmp_path, bundle.manifest, release)


@pytest.mark.parametrize(
    "symbols", [["A10", "missing"], ["A10", "A10"], ["A0"], [f"A{i}" for i in range(11)]]
)
def test_web_scope_rejects_invalid_selection(monkeypatch, tmp_path, symbols):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    with pytest.raises(ValueError, match="2–10"):
        strategy.validate_web_request(
            dict(
                symbols=symbols,
                portfolioMode="shared_account",
                startDate=request(source).start_date.isoformat(),
            ),
            provider,
        )


def test_provider_catalog_type_must_match_reviewed_scope(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    provider.list_assets = lambda **_: [SimpleNamespace(symbol="A10", asset_type="etf")]
    with pytest.raises(ValueError, match="资产类型"):
        strategy.run_joint(BacktestEngine(provider, {}), request(source))


def test_ten_mixed_assets_and_full_cash_reserve_have_consistent_target(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    engine = BacktestEngine(provider, {"portfolio_ppo": strategy})
    selected = tuple(list(source)[2:])
    result, weights = strategy.run_joint(
        engine,
        request(source, symbols=selected, cash_pct=100),
        with_target=True,
    )
    assert len(weights) == 10 and set(weights.values()) == {0.0}
    assert not result.trades
    assert all(p["equity"] == 100000 and p["cashCny"] == 100000 for p in result.account_curve)


def test_new_scope_rejects_provider_universe_version_on_direct_execution(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    provider.publication_context = {"universeVersion": "changed"}
    with pytest.raises(ValueError, match="目录版本"):
        strategy.run_joint(BacktestEngine(provider, {}), request(source))


def test_first_day_verified_suspension_uses_real_prior_benchmark_valuation(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    day = source["A10"].date.iloc[211]
    prior = float(source["A10"].close.iloc[210])
    source["A10"] = source["A10"].drop(index=211)
    provider.nontrading_sessions = lambda symbol, *_: {day} if symbol == "A10" else set()
    current = request(source, benchmark_mode="buy_and_hold")
    result = BacktestEngine(provider, {"portfolio_ppo": strategy}).run(current)
    assert result.equity_curve.benchmarkEquity.iloc[0] == 1
    expected = (
        float(source["A10"].close.iloc[-1]) / prior
        + float(source["A11"].close.iloc[-1]) / float(source["A11"].close.iloc[211])
    ) / 2
    assert result.equity_curve.benchmarkEquity.iloc[-1] == pytest.approx(expected)
    assert all(t.symbol != "A10" or t.trade_date != day.date() for t in result.trades)


def test_benchmark_never_fills_unknown_first_day_or_missing_prelisting_price(monkeypatch, tmp_path):
    source, _, _, _, provider = released(monkeypatch, tmp_path)
    day = source["A10"].date.iloc[211]
    source["A10"] = source["A10"].drop(index=211)
    current = request(source, benchmark_mode="buy_and_hold")
    dates = pd.DatetimeIndex(source["A11"].date.iloc[211:])
    engine = BacktestEngine(provider, {})
    with pytest.raises(ValueError, match="未经核实"):
        engine._benchmark_curve(current, dates)
    provider.nontrading_sessions = lambda symbol, *_: {day} if symbol == "A10" else set()
    source["A10"] = source["A10"].loc[source["A10"].date > day]
    with pytest.raises(ValueError, match="没有此前真实收盘价"):
        engine._benchmark_curve(current, dates)


def test_scope_warmup_reports_typed_error_with_affected_symbol(monkeypatch, tmp_path):
    source, _, release, _, provider = released(monkeypatch, tmp_path)
    strategy = JointPortfolioStrategy(tmp_path, release)
    source["A10"] = source["A10"].iloc[180:]
    with pytest.raises(RLInsufficientHistory) as error:
        strategy.run_joint(BacktestEngine(provider, {}), request(source))
    assert error.value.symbol == "A10"
    assert error.value.research_reason


def test_confirmed_suspension_carries_valuation_and_features_but_never_fills(monkeypatch, tmp_path):
    source, bundle, _, _, _ = released(monkeypatch, tmp_path)
    chosen = {s: source[s].copy() for s in ("A10", "A11")}
    missing = chosen["A10"].date.iloc[250]
    chosen["A10"] = chosen["A10"].drop(index=250)
    known = {"A10": {missing}}
    panel = prepare_panel(chosen, nontrading_sessions=known)
    bar = panel.dates.get_loc(missing)
    assert not panel.tradable[bar, 0]
    assert panel.closes[bar, 0] == panel.closes[bar - 1, 0]
    np.testing.assert_array_equal(panel.features[bar, 0], panel.features[bar - 1, 0])
    replay = evaluate_portfolio(
        bundle,
        chosen,
        start=request(source).start_date,
        end=request(source).end_date,
        asset_types={"A10": "stock", "A11": "etf"},
        nontrading_sessions=known,
        trading_costs=TradingCosts(),
        cash_pct=25,
    )
    point = next(p for p in replay["accountCurve"] if p["date"] == missing.date().isoformat())
    assert all(fill["symbol"] != "A10" for fill in point["fills"])
    with pytest.raises(ValueError, match="未经核实"):
        prepare_panel(chosen, nontrading_sessions={})


def test_suspensions_do_not_count_as_warmup_and_later_listing_is_explicit(monkeypatch, tmp_path):
    source, bundle, _, _, _ = released(monkeypatch, tmp_path)
    chosen = {s: source[s].copy() for s in ("A10", "A11")}
    missing = chosen["A10"].date.iloc[100:200].tolist()
    chosen["A10"] = chosen["A10"].drop(index=range(100, 200))
    with pytest.raises(RLInsufficientHistory, match="140"):
        evaluate_portfolio(
            bundle,
            chosen,
            start=request(source).start_date,
            end=request(source).end_date,
            asset_types={"A10": "stock", "A11": "etf"},
            nontrading_sessions={"A10": missing},
        )
    chosen = {"A10": source["A10"].iloc[50:].copy(), "A11": source["A11"].copy()}
    replay = evaluate_portfolio(
        bundle,
        chosen,
        start=request(source).start_date,
        end=request(source).end_date,
        asset_types={"A10": "stock", "A11": "etf"},
        nontrading_sessions={},
    )
    assert replay["startDate"] == request(source).start_date.isoformat()
