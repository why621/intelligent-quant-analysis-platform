"""Opt-in real Tencent -> temporary SQLite -> Flask test-client verification.

Fixed 2026-09-07 as-of; two stocks + existing ETF benchmark, NOT full CSI300.
No production data or deployment changes. Run with repository PYTHONPATH.
"""
import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app import create_app
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.models import Asset


def main():
    start, end = date(2025, 9, 7), date(2026, 9, 7)
    with tempfile.TemporaryDirectory(prefix="quant-chain-") as directory:
        with (
            patch.dict(os.environ, {"QUANT_DATA_DIR": directory}),
            patch("app.tempfile.mkdtemp", return_value=directory),
        ):
            app = create_app({"TESTING": True, "ALLOWED_ORIGINS": "https://why621.github.io"})
        provider = app.extensions["market_data_service"]._provider
        provider._assets = {
            "000001": provider._assets["000001"],
            "600000": Asset(symbol="600000", name="浦发银行", asset_type="stock", exchange="SSE"),
            "510300": provider._assets["510300"],
        }
        for symbol in provider._assets:
            frame = provider.history(symbol, start, end)
            assert not frame.empty and frame.iloc[-1]["date"].date() == end
            print(json.dumps({"history": symbol, "rows": len(frame),
                              "first": str(frame.iloc[0]["date"].date()), "last": str(end),
                              "lastVolume": float(frame.iloc[-1]["volume"])}), flush=True)
        provider._status_storage.save(
            "stale", end, "isolated 2-stock + ETF sample; no market overview",
            components={"history": {"status": "ready", "message": "isolated sample only"},
                        "overview": {"status": "failed", "message": "no snapshot"}})
        reloaded = AkShareMarketDataProvider(Path(directory))
        with patch.object(reloaded, "_fetch_tencent", side_effect=AssertionError("unexpected fetch")):
            assert reloaded.history("000001", start, end).iloc[-1]["volume"] == 108727600
        client = app.test_client()

        def call(method, path, expected=200, **kwargs):
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.json)
            print(json.dumps({"api": path.split("?")[0], "status": expected}), flush=True)
            return response.json

        with (
            patch.object(provider, "_fetch_tencent", side_effect=AssertionError("cache miss")),
            patch("quant_platform.allocation._today", return_value=end + timedelta(days=1)),
        ):
            call("get", "/api/assets")
            call("get", f"/api/assets/000001/history?startDate={start}&endDate={end}")
            call("post", "/api/analytics/correlation", json={
                "symbols": ["000001", "600000"], "startDate": "2026-06-01", "endDate": str(end)})
            job = call("post", "/api/backtests", 202, json={
                "symbols": ["000001", "600000"], "strategyId": "ma_cross",
                "parameters": {"shortWindow": 5, "longWindow": 20},
                "startDate": "2026-06-01", "endDate": str(end), "benchmark": "510300"})
            app.extensions["backtest_service"].execute_job(job["jobId"])
            result = call("get", "/api/backtests/" + job["jobId"])
            assert result["status"] == "succeeded" and result["result"], result
            assert call("get", "/api/strategies/ranking?period=30d")["items"]
            allocation = call("post", "/api/allocation/suggestion", json={
                "symbols": ["000001", "600000"], "strategyId": "ma_cross", "cashPct": 10})
            assert allocation["basisDate"] == str(end)
            assert abs(sum(p["weightPct"] for p in allocation["positions"])
                       + allocation["cashPct"] - 100) < 1e-8
            call("get", "/api/market/overview", 503)
            cors = client.options("/api/analytics/correlation", headers={
                "Origin": "https://why621.github.io", "Access-Control-Request-Method": "POST"})
            assert cors.headers["Access-Control-Allow-Origin"] == "https://why621.github.io"
        print("PASS: isolated real-data research chain; overview unavailable as expected; "
              "benchmark=510300 ETF, not CSI300 index; no browser/cloud acceptance", flush=True)


if __name__ == "__main__":
    main()
