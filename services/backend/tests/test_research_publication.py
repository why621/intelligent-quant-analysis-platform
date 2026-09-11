"""Offline CR-017 regressions: no SDK/network calls and isolated real SQLite."""

from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.data.calendar import sessions
from quant_platform.models import DataStatus

from app import create_app
from app.services.research_dates import DataVersionChangedError, research_read


@pytest.fixture
def stack(tmp_path, monkeypatch):
    provider = AkShareMarketDataProvider(tmp_path)
    provider.status = Mock(
        return_value=DataStatus(
            status="stale",
            source="test",
            asset_count=50,
            latest_trade_date=date(2026, 9, 7),
            updated_at=None,
            components={"history": {"status": "ready"}, "overview": {"status": "failed"}},
        )
    )
    provider._fetch_tencent = Mock(side_effect=AssertionError("research must never fetch"))
    monkeypatch.setattr("quant_platform.allocation._today", lambda: date(2026, 9, 9))
    application = create_app({"TESTING": True}, market_data_provider=provider)
    return provider, application, application.test_client()


def save(provider, symbol, start=date(2025, 9, 7), end=date(2026, 9, 7)):
    dates = pd.to_datetime(sessions(start, end))
    values = [100 + i / 10 for i in range(len(dates))]
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": 1000,
            "amount": 100000,
        }
    )
    provider._save_history_cache(symbol, frame)
    return frame


def test_cross_day_new_asset_cache_does_not_promote_publication(stack):
    provider, _, client = stack
    save(provider, "510300", end=date(2026, 9, 8))
    revision = provider.cache_revision()
    result = client.post(
        "/api/allocation/suggestion", json={"symbols": ["510300"], "strategyId": "ma_cross"}
    )
    assert result.status_code == 503
    assert result.json["error"]["code"] == "DATA_STALE"
    assert result.json["error"]["details"] == {
        "availableEndDate": "2026-09-07",
        "requiredEndDate": "2026-09-08",
    }
    assert provider.cache_revision() == revision
    provider._fetch_tencent.assert_not_called()


@pytest.mark.parametrize("newer", [False, True])
def test_missing_or_unpublished_history_is_read_only(stack, newer):
    provider, _, client = stack
    if newer:
        save(provider, "510300", end=date(2026, 9, 8))
    revision = provider.cache_revision()
    result = client.get("/api/assets/510300/history?startDate=2025-09-07&endDate=2026-09-07")
    assert result.status_code == 503
    assert result.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert provider.cache_revision() == revision
    provider._fetch_tencent.assert_not_called()


def test_valid_old_history_and_overview_failure_are_independent(stack):
    provider, _, client = stack
    save(provider, "510300")
    status = client.get("/api/data/status").json
    response = client.get("/api/assets/510300/history?startDate=2025-09-07&endDate=2026-09-07")
    assert response.status_code == 200
    assert response.json["dataContext"] == status["dataContext"]
    assert len(response.json["items"]) == 242
    provider._fetch_tencent.assert_not_called()


@pytest.mark.parametrize("state", ["updating", "failed"])
def test_partial_update_rejects_research(stack, state):
    provider, _, client = stack
    provider.status.return_value.components["history"]["status"] = state
    response = client.get("/api/assets/510300/history?startDate=2025-09-07&endDate=2026-09-07")
    assert response.status_code == 503
    assert response.json["error"]["code"] == "DATA_NOT_READY"
    assert client.get("/api/data/status").json["dataContext"] is None


def test_revision_change_during_read_rejects_result_and_resets_scope(stack):
    provider, _, _ = stack
    with pytest.raises(DataVersionChangedError):
        with research_read(provider):
            save(provider, "510300")
    # The ContextVar must reset even after failure; explicit acquisition is still distinct.
    with pytest.raises(AssertionError, match="never fetch"):
        provider.history("510500", date(2026, 9, 1), date(2026, 9, 7))


def test_page_version_header_refuses_newer_revision(stack):
    provider, _, client = stack
    old = client.get("/api/data/status").json["dataContext"]["dataVersion"]
    save(provider, "510300")
    result = client.get(
        "/api/assets/510300/history?startDate=2025-09-07&endDate=2026-09-07",
        headers={"X-Research-Version": old},
    )
    assert result.status_code == 409
    assert result.json["error"]["code"] == "DATA_VERSION_CHANGED"


def test_queued_job_refuses_new_revision_preserves_request_and_context(stack):
    provider, application, client = stack
    payload = {
        "symbols": ["510300"],
        "strategyId": "ma_cross",
        "parameters": {"shortWindow": 5, "longWindow": 20},
        "startDate": "2025-09-07",
        "endDate": "2026-09-07",
    }
    response = client.post("/api/backtests", json=payload)
    assert response.status_code == 202
    original = response.json
    save(provider, "510300")
    service = application.extensions["backtest_service"]
    service._engine.run = Mock(side_effect=AssertionError("must not recompute"))
    service.execute_job(original["jobId"])
    result = client.get("/api/backtests/" + original["jobId"]).json
    assert result["status"] == "failed"
    assert result["error"]["error"]["code"] == "DATA_VERSION_CHANGED"
    assert result["request"] == payload
    assert result["dataContext"] == original["dataContext"]
    service._engine.run.assert_not_called()


def test_current_publication_allocation_uses_same_context(stack, monkeypatch):
    provider, _, client = stack
    monkeypatch.setattr("quant_platform.allocation._today", lambda: date(2026, 9, 8))
    save(provider, "510300")
    result = client.post(
        "/api/allocation/suggestion", json={"symbols": ["510300"], "strategyId": "ma_cross"}
    )
    assert result.status_code == 200
    assert result.json["basisDate"] == "2026-09-07"
    assert result.json["targetDate"] == "2026-09-08"
    assert result.json["dataContext"] == client.get("/api/data/status").json["dataContext"]
    provider._fetch_tencent.assert_not_called()


def test_explicit_index_benchmark_context_and_job_execution(stack):
    from quant_platform.data.index_snapshot import INDEX_ID, IndexSnapshot

    provider, application, client = stack
    frame = save(provider, "510300")
    original = client.get("/api/data/status").json["dataContext"]
    provider.index_snapshot = IndexSnapshot(
        date(2025, 9, 7),
        date(2026, 9, 7),
        "a" * 64,
        tuple(
            (row.date.date().isoformat(), row.open, row.high, row.low, row.close)
            for row in frame.itertuples()
        ),
    )
    status = client.get("/api/data/status").json
    assert status["benchmarks"][0]["assetId"] == INDEX_ID
    assert status["dataContext"] != original
    payload = {
        "symbols": ["510300"],
        "strategyId": "ma_cross",
        "parameters": {"shortWindow": 5, "longWindow": 20},
        "startDate": "2025-09-07",
        "endDate": "2026-09-07",
        "benchmark": INDEX_ID,
    }
    accepted = client.post("/api/backtests", json=payload)
    assert accepted.status_code == 202
    service = application.extensions["backtest_service"]
    service.execute_job(accepted.json["jobId"])
    result = client.get("/api/backtests/" + accepted.json["jobId"]).json
    assert result["status"] == "succeeded", result
    assert result["result"]["assumptions"]["benchmarkReturnBasis"] == "price_index"
    assert result["result"]["equityCurve"][-1]["benchmarkEquity"] is not None
    provider._fetch_tencent.assert_not_called()
