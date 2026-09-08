"""Synthetic directory only; NOT real CSI300 constituents."""
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest
from quant_platform.models import Asset, DataStatus

from app import create_app


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))
    app = create_app({"TESTING": True})
    provider = app.extensions["market_data_service"]._provider
    assets = [Asset(f"{600000 + n}", f"合成股票{n}", "stock", "SSE")
              for n in range(300)]
    assets += [Asset(f"{510000 + n}", f"合成ETF{n}", "etf", "SSE")
               for n in range(101)]
    provider._assets = {a.symbol: a for a in reversed(assets)}
    provider.status = Mock(return_value=DataStatus(
        status="ready", source="AkShare", asset_count=len(assets),
        latest_trade_date=date(2026, 9, 7), updated_at=None,
    ))
    provider.history = Mock(return_value=pd.DataFrame())
    return app.test_client(), provider


def test_full_pagination(catalog):
    client, provider = catalog
    items, versions, offset = [], set(), 0
    while offset is not None:
        page = client.get(f"/api/assets?limit=100&offset={offset}").json
        assert page["matchedTotal"] == 401
        assert page["offset"] == offset
        assert page["total"] == len(page["items"])
        items.extend(page["items"])
        versions.add(page["catalogVersion"])
        offset = page["nextOffset"]
    assert len(items) == len({item["assetId"] for item in items}) == 401
    assert [item["symbol"] for item in items] == sorted(provider._assets)
    assert len(versions) == 1
    assert len(provider.list_assets(limit=None)) == 401
    assert len(provider.list_assets()) == 50
    assert client.get("/api/assets?limit=5").json["total"] == 5
    assert client.get("/api/assets?offset=999").json["items"] == []


def test_filter_and_revision(catalog):
    client, provider = catalog
    page = client.get("/api/assets?assetType=stock&offset=200&limit=100").json
    assert page["total"] == 100 and page["matchedTotal"] == 300
    assert page["nextOffset"] is None
    assert page["items"][-1]["assetId"] == "stock:SSE:600299"
    found = client.get("/api/assets?query=600299").json
    assert found["matchedTotal"] == 1
    assert found["catalogVersion"] == page["catalogVersion"]
    assert client.get("/api/assets?query=不存在").json["matchedTotal"] == 0
    provider._assets["600299"] = Asset("600299", "改名", "stock", "SSE")
    assert client.get("/api/assets").json["catalogVersion"] != page["catalogVersion"]


@pytest.mark.parametrize("offset", ["-1", "1.5", "abc", "100001", "9" * 5000],
                         ids=["negative", "fraction", "text", "over-limit", "huge"])
def test_invalid_offset(catalog, offset):
    client, _ = catalog
    response = client.get("/api/assets", query_string={"offset": offset})
    assert response.status_code == 400
    assert response.json["error"]["details"]["field"] == "offset"


def test_tail_membership(catalog):
    client, provider = catalog
    response = client.get(
        "/api/assets/600000/history?startDate=2026-09-04&endDate=2026-09-07")
    assert response.status_code == 200
    provider.history.assert_called_once()
    response = client.post("/api/backtests", json={
        "symbols": ["600000"], "strategyId": "ma_cross",
        "parameters": {"shortWindow": 5, "longWindow": 20},
        "startDate": "2025-09-07", "endDate": "2026-09-07",
        "benchmark": "510000",
    })
    assert response.status_code == 202
    assert client.get("/api/assets/999999/history?startDate=2026-09-04"
                      "&endDate=2026-09-07").status_code == 404
