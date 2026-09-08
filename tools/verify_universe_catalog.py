"""Offline official snapshot -> shared provider -> Flask directory verification.

Reads a validated snapshot, uses a NEW artifact directory for empty data.
Does not fetch history, start a server/worker, or publish a universe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import create_app
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.data.universe import load_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifacts = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(artifacts) or output == artifacts or output.exists():
        parser.error("--output must be a NEW directory under artifacts")
    snapshot = load_snapshot(args.snapshot)
    output.mkdir(parents=True, exist_ok=False)
    provider = AkShareMarketDataProvider(output / "empty-market", universe_snapshot=snapshot)

    def no_network(*args, **kwargs):
        raise AssertionError("directory verification must not request market data")

    provider._fetch_tencent = no_network
    provider._fetch_market_overview = no_network
    application = create_app({"TESTING": True}, market_data_provider=provider)
    client = application.test_client()
    assets, versions, offsets, offset = [], set(), [], 0
    while offset is not None:
        offsets.append(offset)
        response = client.get("/api/assets", query_string={"limit": 100, "offset": offset})
        assert response.status_code == 200
        page = response.json
        assert page["offset"] == offset and page["total"] == len(page["items"])
        versions.add(page["catalogVersion"])
        assets.extend(page["items"])
        offset = page["nextOffset"]
        assert len(offsets) <= 10
    assert len(versions) == 1 and len(assets) == page["matchedTotal"]
    stocks = [a for a in assets if a["assetType"] == "stock"]
    etfs = [a for a in assets if a["assetType"] == "etf"]
    assert {a["symbol"] for a in stocks} == {a.symbol for a in snapshot.members}
    assert len(stocks) == 300 and len({a["assetId"] for a in assets}) == len(assets)
    assert len(etfs) == 27
    last = snapshot.members[-1].symbol
    assert client.get("/api/assets", query_string={"query": last}).json["matchedTotal"] == 1
    status = client.get("/api/data/status").json
    assert status["latestTradeDate"] is None and status["status"] != "ready"
    rejected = client.post("/api/backtests", json={
        "symbols": [last], "strategyId": "ma_cross",
        "parameters": {"shortWindow": 5, "longWindow": 20},
        "startDate": "2025-09-07", "endDate": "2026-09-07",
    })
    assert rejected.status_code == 503
    assert rejected.json["error"]["code"] == "DATA_NOT_READY"
    evidence = {
        "level": "offline Flask test-client / official snapshot / no market data",
        "snapshotId": snapshot.to_dict()["snapshotId"], "catalogVersion": next(iter(versions)),
        "stocks": len(stocks), "etfs": len(etfs), "total": len(assets), "pageOffsets": offsets,
        "tailQuery": last, "latestTradeDate": None,
        "emptyDataBacktest": rejected.json["error"]["code"],
        "networkRequests": 0, "productionWrites": False,
    }
    (output / "catalog-evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
