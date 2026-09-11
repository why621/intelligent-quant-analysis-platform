from datetime import date
from unittest.mock import Mock

import pytest
from quant_platform.data.akshare_provider import UpstreamUnavailableError
from quant_platform.models import CorrelationResult, DataStatus

from app import create_app


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path / "market"))
    application = create_app({"TESTING": True})
    provider = application.extensions["market_data_service"]._provider
    provider.status = Mock(return_value=DataStatus(
        status="stale", source="AkShare", asset_count=50,
        latest_trade_date=date(2026, 9, 7), updated_at=None,
        components={"history": {"status": "ready"}, "overview": {"status": "failed"}},
    ))
    provider.history = Mock(side_effect=UpstreamUnavailableError("controlled outage"))
    return application, provider, application.test_client()


def body(client, strategy_id="ma_cross"):
    metadata = next(item for item in client.get("/api/strategies").json["items"]
                    if item["id"] == strategy_id)
    return {
        "symbols": ["510300"], "strategyId": strategy_id,
        "parameters": {key: value["default"]
                       for key, value in metadata["parameterSchema"]["properties"].items()},
        "startDate": "2025-09-07", "endDate": "2026-09-07",
    }


@pytest.mark.parametrize("strategy", ["ma_cross", "momentum_reversal"])
def test_server_metadata_defaults_create_recoverable_job(stack, strategy):
    _, _, client = stack
    payload = body(client, strategy)
    response = client.post("/api/backtests", json=payload)
    assert response.status_code == 202
    job = client.get("/api/backtests/" + response.json["jobId"]).json
    assert job["request"] == payload
    assert "benchmark" not in job["request"]
    payload["parameters"] = {}
    invalid = client.post("/api/backtests", json=payload)
    assert invalid.status_code == 400
    assert invalid.json["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("endpoint", ["/api/backtests", "/api/analytics/correlation"])
@pytest.mark.parametrize("start,end", [
    ("2025-09-07", "2026-09-08"), ("2024-12-31", "2026-09-07"),
    ("2026-09-07", "2027-01-01"),
])
def test_out_of_range_is_synchronous_and_never_calls_upstream(stack, endpoint, start, end):
    application, provider, client = stack
    payload = body(client) if endpoint.endswith("backtests") else {
        "symbols": ["510300", "510500", "159915"]}
    payload.update(startDate=start, endDate=end)
    response = client.post(endpoint, json=payload)
    assert response.status_code == 400
    error = response.json["error"]
    assert error["code"] == "DATE_OUT_OF_RANGE"
    assert error["details"]["availableEndDate"] == "2026-09-07"
    assert error["details"]["startDate"] == start
    assert error["details"]["endDate"] == end
    assert error["details"]["symbols"] == payload["symbols"]
    provider.history.assert_not_called()
    assert application.extensions["backtest_service"]._store.claim() is None


@pytest.mark.parametrize("missing,failed", [(True, False), (False, True)])
def test_missing_or_failed_publication_rejects_both_endpoints(stack, missing, failed):
    _, provider, client = stack
    provider.status.return_value = DataStatus(
        status="failed" if failed else "updating", source="AkShare", asset_count=50,
        latest_trade_date=None if missing else date(2026, 9, 7), updated_at=None,
    )
    for endpoint, payload in [
        ("/api/backtests", body(client)),
        ("/api/analytics/correlation", {
            "symbols": ["510300", "510500"], "startDate": "2025-09-07", "endDate": "2026-09-07"}),
    ]:
        response = client.post(endpoint, json=payload)
        assert response.status_code == 503
        assert response.json["error"]["code"] == "DATA_NOT_READY"
    provider.history.assert_not_called()


def test_in_range_source_failure_stays_upstream_unavailable(stack):
    application, provider, client = stack
    response = client.post("/api/analytics/correlation", json={
        "symbols": ["510300", "510500", "159915"],
        "startDate": "2025-09-07", "endDate": "2026-09-07",
    })
    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert provider.history.called
    accepted = client.post("/api/backtests", json=body(client)).json
    application.extensions["backtest_service"].execute_job(accepted["jobId"])
    failed = client.get("/api/backtests/" + accepted["jobId"]).json
    assert failed["error"]["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_overview_failure_does_not_block_valid_correlation(stack):
    application, _, client = stack
    service = application.extensions["correlation_service"]
    service._analyzer.calculate = Mock(return_value=CorrelationResult(
        symbols=("510300", "510500", "159915"), observation_count=242,
        matrix=((1, .8, .6), (.8, 1, .7), (.6, .7, 1)),
    ))
    response = client.post("/api/analytics/correlation", json={
        "symbols": ["510300", "510500", "159915"],
        "startDate": "2025-09-07", "endDate": "2026-09-07",
    })
    assert response.status_code == 200
    assert response.json["observationCount"] == 242


@pytest.mark.parametrize("benchmark", ["000300", "600519", "999999"])
def test_unimplemented_index_stock_or_unknown_benchmark_cannot_enqueue(stack, benchmark):
    application, _, client = stack
    response = client.post("/api/backtests", json=dict(body(client), benchmark=benchmark))
    assert response.status_code == 400
    assert response.json["error"]["details"]["field"] == "benchmark"
    assert application.extensions["backtest_service"]._store.claim() is None


def test_explicit_etf_benchmark_is_preserved(stack):
    _, _, client = stack
    payload = dict(body(client), benchmark="510500")
    response = client.post("/api/backtests", json=payload)
    assert response.status_code == 202
    assert response.json["request"]["benchmark"] == "510500"


def test_metadata_relations_match_backend_business_constraints(stack):
    _, _, client = stack
    for strategy in client.get("/api/strategies").json["items"]:
        payload = body(client, strategy["id"])
        relation = strategy["parameterSchema"]["x-relations"][0]
        assert relation["operator"] == "lt"
        payload["parameters"][relation["left"]] = payload["parameters"][relation["right"]]
        response = client.post("/api/backtests", json=payload)
        assert response.status_code == 400
        assert response.json["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_strategy_parameters_never_enqueue(stack, value):
    application, _, client = stack
    payload = body(client, "momentum_reversal")
    payload["parameters"]["overboughtThreshold"] = value
    response = client.post("/api/backtests", json=payload)
    assert response.status_code == 400
    assert application.extensions["backtest_service"]._store.claim() is None
