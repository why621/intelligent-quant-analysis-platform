"""CR069: real engine parity, exact research inputs and bounded cache isolation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Event
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from quant_platform.data.calendar import sessions
from quant_platform.models import Asset, DataStatus
from quant_platform.strategies.ma_cross import MACrossStrategy

from app import create_app
from app.services.errors import UpstreamUnavailableError


class Provider:
    start = date(2026, 1, 1)
    revision = "revision-a"

    def __init__(self):
        dates = pd.to_datetime(sessions(self.start, date(2026, 9, 30)))
        prices = 10 + np.sin(np.arange(len(dates)) / 3) + np.arange(len(dates)) / 100
        self.frames = {}
        self.assets = [Asset("600000", "Stock", "stock", "SSE"),
                       Asset("510300", "ETF", "etf", "SSE")]
        for i, asset in enumerate(self.assets):
            close = prices * (i + 1)
            self.frames[asset.symbol] = pd.DataFrame({
                "date": dates, "open": close * 1.001, "high": close * 1.02,
                "low": close * .98, "close": close, "volume": 10000.0,
            })

    def list_assets(self, query=None, asset_type=None, limit=None):
        return [asset for asset in self.assets if not asset_type or asset.asset_type == asset_type]

    def history(self, symbol, start_date, end_date, adjust="qfq"):
        frame = self.frames[symbol]
        return frame[(frame.date >= pd.Timestamp(start_date))
                     & (frame.date <= pd.Timestamp(end_date))].reset_index(drop=True).copy()

    def cache_revision(self):
        return self.revision

    def status(self):
        return DataStatus("ready", "offline-test", len(self.assets), date(2026, 9, 30), None)


@pytest.fixture
def setup():
    app = create_app({"TESTING": True, "QUANT_RL_RELEASE": None,
                      "QUANT_PORTFOLIO_RELEASE": None}, market_data_provider=Provider())
    return app, app.test_client(), app.extensions["ranking_service"]


@pytest.fixture
def request_config():
    return {"symbols": ["600000", "510300"], "strategyId": "ma_cross",
            "startDate": "2026-07-01", "endDate": "2026-09-18",
            "parameters": {"shortWindow": 3, "longWindow": 12},
            "initialCapitalCny": 150000, "cashPct": 15,
            "portfolioMode": "shared_account", "benchmarkMode": "buy_and_hold",
            "adjust": "qfq", "tradingCosts": {"commissionPct": .08,
            "stampDutyPct": .07, "slippagePct": .04, "stampDutyMode": "asset_date"}}


def post(client, config):
    return client.post("/api/strategies/ranking", json=config)


def test_real_rank_metrics_fees_parameters_equal_persisted_backtests(setup, request_config):
    app, client, _ = setup
    response = post(client, request_config)
    assert response.status_code == 200, response.json
    result = response.json
    assert result["request"] == request_config
    assert result["evaluationSymbols"] == request_config["symbols"]
    assert result["evaluationStartDate"] == request_config["startDate"]
    assert result["evaluationEndDate"] == request_config["endDate"]
    assert result["items"] and not result["unavailableStrategies"]
    service = app.extensions["backtest_service"]
    for item in result["items"]:
        body = {**request_config, "strategyId": item["strategyId"],
                "parameters": item["parameters"]}
        submitted = client.post("/api/backtests", json=body)
        assert submitted.status_code == 202
        job = submitted.json
        service.execute_job(job["jobId"])
        actual = service.get_job(job["jobId"])
        assert actual["status"] == "succeeded", actual
        assert item["metrics"] == actual["result"]["metrics"]
        assert item["costSummary"] == actual["result"]["costSummary"]
        assert item["benchmarkContext"] == actual["result"]["benchmarkContext"]
        assert item["returnPct"] == actual["result"]["metrics"]["totalReturnPct"]
        assert len(actual["result"]["equityCurve"]) == result["observationCount"]
    selected = next(item for item in result["items"] if item["strategyId"] == "ma_cross")
    assert selected["parameters"] == request_config["parameters"]
    other = next(item for item in result["items"] if item["strategyId"] == "momentum_reversal")
    assert other["parameters"]["lookback"] == 10


@pytest.mark.parametrize("change", [
    {"symbols": ["510300"]}, {"symbols": ["510300", "600000"]},
    {"startDate": "2026-07-02"}, {"endDate": "2026-09-17"},
    {"initialCapitalCny": 170000}, {"cashPct": 25}, {"adjust": "none"},
    {"benchmarkMode": "none"}, {"benchmarkMode": "custom", "benchmark": "510300"},
    {"parameters": {"shortWindow": 5, "longWindow": 14}},
    {"tradingCosts": {"commissionPct": .2, "stampDutyPct": .05,
                      "slippagePct": .02, "stampDutyMode": "fixed"}},
    {"portfolioMode": "legacy_independent", "cashPct": 0},
    {"strategyId": "momentum_reversal", "parameters": {
        "lookback": 20, "oversoldThreshold": -3, "overboughtThreshold": 2}},
])
def test_full_configuration_isolates_cache(setup, request_config, change):
    _, client, service = setup
    first = post(client, request_config)
    second = post(client, {**request_config, **change})
    assert first.status_code == 200, first.json
    assert second.status_code == 200, second.json
    assert first.json["configHash"] != second.json["configHash"]
    assert len(service._research_cache) == 2


def test_cache_copy_and_revision_identity(setup, request_config):
    _, _, service = setup
    with patch.object(service._backtests._engine, "run",
                      wraps=service._backtests._engine.run) as run:
        first = service.get_research_ranking(request_config)
        count = run.call_count
        first["request"]["symbols"].clear()
        second = service.get_research_ranking(request_config)
        assert second["request"]["symbols"] == request_config["symbols"]
        assert run.call_count == count
        service._provider.revision = "revision-b"
        third = service.get_research_ranking(request_config)
        assert run.call_count == count * 2
        assert third["configHash"] != second["configHash"]


def test_model_context_and_default_changes_invalidate_cache(setup, request_config):
    _, _, service = setup
    strategy = service._catalog.get_strategy("momentum_reversal")
    context = {"bundleHash": "a" * 64}
    strategy.model_context = lambda: dict(context)
    first = service.get_research_ranking(request_config)
    context["bundleHash"] = "b" * 64
    second = service.get_research_ranking(request_config)
    assert first["configHash"] != second["configHash"]
    original_info = strategy.info
    def changed_info():
        info = original_info()
        schema = deepcopy(info.parameter_schema)
        schema["properties"]["lookback"]["default"] = 12
        return replace(info, parameter_schema=schema)
    strategy.info = changed_info
    third = service.get_research_ranking(request_config)
    assert third["configHash"] != second["configHash"]


def test_incompatible_legacy_ai_is_explained_without_symbol_fallback(setup, request_config):
    _, _, service = setup
    class LegacyAI(MACrossStrategy):
        id = "legacy_ai"
        backtest_enabled = True
        def info(self):
            return replace(super().info(), category="ai", status="experimental",
                           requires_trained_model=True)
    legacy = LegacyAI()
    service._catalog._by_id[legacy.id] = legacy
    service._backtests._engine._strategies[legacy.id] = legacy
    result = service.get_research_ranking(request_config)
    excluded = result["unavailableStrategies"]
    assert excluded == [{"strategyId": "legacy_ai", "strategyName": "均线交叉",
                         "code": "VALIDATION_ERROR", "message": "旧单资产模型不能用于共享组合账户"}]
    assert result["evaluationSymbols"] == ["600000", "510300"]


def test_partial_candidate_and_selected_failure_do_not_fabricate_results(setup, request_config):
    _, client, service = setup
    original = service._backtests._engine.run
    def failed_other(request):
        if request.strategy_id == "momentum_reversal":
            raise ValueError("测试样本不足")
        return original(request)
    with patch.object(service._backtests._engine, "run", side_effect=failed_other):
        result = post(client, request_config)
        assert result.status_code == 200
        assert len(result.json["items"]) == 1
        assert result.json["unavailableStrategies"][0]["message"] == "测试样本不足"
    service._research_cache.clear()
    with patch.object(service._backtests._engine, "run", side_effect=ValueError("样本不足")):
        result = post(client, request_config)
        assert result.status_code == 422
    assert not service._research_cache and not service._research_inflight


def test_shortened_curve_rejected_not_silently_compared(setup, request_config):
    _, client, service = setup
    original = service._backtests._engine.run
    def shortened(request):
        result = original(request)
        return replace(result, equity_curve=result.equity_curve.iloc[1:])
    with patch.object(service._backtests._engine, "run", side_effect=shortened):
        result = post(client, request_config)
    assert result.status_code == 422
    assert "评价交易日" in result.json["error"]["message"]
    assert not service._research_cache


@pytest.mark.parametrize("kind", ["revision", "model", "late"])
def test_changed_or_late_computation_never_cached(setup, request_config, kind):
    _, _, service = setup
    original = service._backtests._engine.run
    def changed(request):
        result = original(request)
        if kind == "revision":
            service._provider.revision += "x"
        elif kind == "model":
            service._catalog.get_strategy("ma_cross").backtest_enabled = True
        return result
    with patch.object(service._backtests._engine, "run", side_effect=changed):
        with patch("app.services.ranking._RESEARCH_BUDGET_SECONDS", 0 if kind == "late" else 30):
            with pytest.raises(UpstreamUnavailableError):
                service.get_research_ranking(request_config)
    assert not service._research_cache and not service._research_inflight


def test_singleflight_same_configuration_computes_once(setup, request_config):
    _, _, service = setup
    started, release = Event(), Event()
    original = service._backtests._engine.run
    def blocked(request):
        started.set()
        assert release.wait(timeout=5)
        return original(request)
    with patch.object(service._backtests._engine, "run", side_effect=blocked) as run:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.get_research_ranking, request_config)
            assert started.wait(5)
            second = pool.submit(service.get_research_ranking, request_config)
            release.set()
            assert first.result(timeout=10) == second.result(timeout=10)
        assert run.call_count == 2  # Two strategies, not two rankings.
    assert not service._research_inflight


def test_parallel_limit_and_cache_size(setup, request_config):
    _, _, service = setup
    service._research_inflight.update({"unrelated-a", "unrelated-b"})
    with pytest.raises(UpstreamUnavailableError, match="繁忙"):
        service.get_research_ranking(request_config)
    service._research_inflight.clear()
    with patch("app.services.ranking._CACHE_LIMIT", 2):
        for cash in (1, 2, 3):
            service.get_research_ranking({**request_config, "cashPct": cash})
    assert len(service._research_cache) == 2


@pytest.mark.parametrize("change,expected", [
    ({"symbols": []}, 400), ({"symbols": ["600000"] * 2}, 400),
    ({"symbols": [f"{i:06}" for i in range(11)]}, 400),
    ({"symbols": ["999999"]}, 404), ({"cashPct": 101}, 400),
    ({"endDate": "2027-09-30"}, 400), ({"startDate": "2026-09-20"}, 400),
    ({"parameters": {"shortWindow": 12, "longWindow": 3}}, 400),
    ({"tradingCosts": {"commissionPct": float("nan")}}, 400),
    ({"benchmarkMode": "custom"}, 400), ({"wrong": 1}, 400),
    ({"strategyId": "missing_strategy"}, 422),
    ({"startDate": "20260701"}, 400),
    ({"parameters": {"shortWindow": 3, "longWindow": float("nan")}}, 400),
])
def test_request_boundaries(setup, request_config, change, expected):
    _, client, service = setup
    result = post(client, {**request_config, **change})
    assert result.status_code == expected, result.json
    assert not service._research_cache


def test_contract_and_no_job_write(setup, request_config):
    import sqlite3

    import jsonschema
    import yaml
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    app, client, _ = setup
    root = Path(__file__).resolve().parents[3] / "packages/contracts"
    schemas = root / "schemas"
    store = {(schemas / filename).as_uri(): yaml.safe_load((schemas / filename).read_text())
             for filename in ("strategy.yaml", "common.yaml", "backtest.yaml")}
    registry = Registry().with_resources((uri, Resource.from_contents(value,
                    default_specification=DRAFT202012)) for uri, value in store.items())
    response = post(client, request_config)
    assert response.status_code == 200
    jsonschema.Draft202012Validator(
        {"$ref": (schemas / "strategy.yaml").as_uri() + "#/ResearchRankingResponse"},
                                    registry=registry,
                                    format_checker=jsonschema.FormatChecker()).validate(response.json)
    jsonschema.Draft202012Validator(
        {"$ref": (schemas / "strategy.yaml").as_uri() + "#/ResearchRankingRequest"},
                                    registry=registry,
                                    format_checker=jsonschema.FormatChecker()).validate(request_config)
    paths = yaml.safe_load((root / "openapi.yaml").read_text())["paths"]
    assert "post" in paths["/strategies/ranking"] and "get" in paths["/strategies/ranking"]
    with sqlite3.connect(app.extensions["backtest_service"]._store._db_path) as db:
        assert db.execute("SELECT count(*) FROM backtest_jobs").fetchone()[0] == 0


def test_joint_models_receive_same_request_cost_cash_and_parameters(setup, request_config):
    _, _, service = setup
    class Joint(MACrossStrategy):
        id = "portfolio_test"
        backtest_enabled = True
        joint_portfolio = True
        def info(self):
            return replace(super().info(), category="ai", status="experimental",
                           requires_trained_model=True)
        def validate_web_request(self, payload, provider):
            assert payload["symbols"] == request_config["symbols"]
            assert payload["cashPct"] == request_config["cashPct"]
            assert payload["tradingCosts"] == request_config["tradingCosts"]
        def model_context(self):
            return {"bundleHash": "a" * 64, "costPolicy": "request_configurable"}
        def run_joint(self, engine, request):
            assert request.initial_capital_cny == request_config["initialCapitalCny"]
            assert request.cash_pct == request_config["cashPct"]
            return engine._run_shared(replace(request, strategy_id="ma_cross"))
    joint = Joint()
    service._catalog._by_id[joint.id] = joint
    service._backtests._engine._strategies[joint.id] = joint
    result = service.get_research_ranking(request_config)
    item = next(item for item in result["items"] if item["strategyId"] == joint.id)
    assert item["parameters"] == {"shortWindow": 5, "longWindow": 20}
    assert item["modelContext"]["costPolicy"] == "request_configurable"
    assert not result["unavailableStrategies"]


def test_transient_partial_failure_not_cached_and_retry_recovers(setup, request_config):
    _, _, service = setup
    original = service._backtests._engine.run
    def partial(request):
        if request.strategy_id == "momentum_reversal":
            raise RuntimeError("transient engine failure")
        return original(request)
    with patch.object(service._backtests._engine, "run", side_effect=partial):
        result = service.get_research_ranking(request_config)
    assert result["unavailableStrategies"][0]["code"] == "RANKING_FAILED"
    assert not service._research_cache
    assert len(service.get_research_ranking(request_config)["items"]) == 2


def test_budget_enforced_after_expensive_computation(setup, request_config):
    _, _, service = setup
    clock = [100.0]
    original = service._backtests._engine.run
    def late(request):
        result = original(request)
        if request.strategy_id == "momentum_reversal":
            clock[0] += 31
        return result
    with patch("app.services.ranking.monotonic", side_effect=lambda: clock[0]):
        with patch.object(service._backtests._engine, "run", side_effect=late):
            with pytest.raises(UpstreamUnavailableError, match="超时"):
                service.get_research_ranking(request_config)
    assert not service._research_cache and not service._research_inflight


def test_singleflight_wait_deadline_and_upstream_failure_cleanup(setup, request_config):
    from quant_platform.data.akshare_provider import UpstreamUnavailableError as ProviderError

    from app.services.ranking import _digest, _normalize_request
    from app.services.research_dates import research_context

    _, _, service = setup
    key = _digest({"request": _normalize_request(request_config),
                   "data": research_context(service._provider),
                   "revision": service._revision(), "strategies": service._model_identity()})
    service._research_inflight.add(key)
    with patch("app.services.ranking._RESEARCH_BUDGET_SECONDS", 0):
        with pytest.raises(UpstreamUnavailableError, match="繁忙"):
            service.get_research_ranking(request_config)
    assert key in service._research_inflight
    service._research_inflight.clear()
    with patch.object(service._backtests, "validate_request", side_effect=ProviderError("offline")):
        with pytest.raises(UpstreamUnavailableError):
            service.get_research_ranking(request_config)
    assert not service._research_cache and not service._research_inflight
