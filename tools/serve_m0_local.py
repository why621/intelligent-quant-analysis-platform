"""Isolated M0 validation host: sampled real history, built UI and actual worker.

Run from the repo root with PYTHONPATH=services/algorithms/src:services/backend/src.
--prepare fetches only the three default ETFs into a NEW directory.
Serving disables further upstream history requests and binds only to loopback.
This is sample validation, not a daily publication or a full-universe acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOLS = ("510300", "510500", "159915")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    os.environ["QUANT_DATA_DIR"] = str(data_dir)
    os.environ["BACKTEST_DB_PATH"] = str(data_dir / "backtests.db")
    from quant_platform.data.akshare_provider import AkShareMarketDataProvider
    from quant_platform.data.calendar import latest_session

    if args.prepare:
        if data_dir.exists():
            raise SystemExit("--prepare requires a NEW directory; existing data is never overwritten")
        data_dir.mkdir(parents=True)
        provider = AkShareMarketDataProvider(data_dir=data_dir)
        provider._assets = {key: provider._assets[key] for key in SYMBOLS}
        end = latest_session(datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1))
        start = end.replace(year=end.year - 1)
        rows = {}
        for symbol in SYMBOLS:
            frame = provider.history(symbol, start, end, "qfq")
            rows[symbol] = {"count": len(frame), "first": str(frame["date"].min().date()),
                            "last": str(frame["date"].max().date())}
            print(json.dumps({symbol: rows[symbol]}, ensure_ascii=False), flush=True)
        # history() has already enforced full sessions and storage price/volume validation.
        provider._status_storage.save(
            "stale", end, "M0隔离真实样本：3只ETF；不是全量日更",
            components={
                "history": {"status": "ready", "message": "3只默认ETF区间完整性通过"},
                "overview": {"status": "failed", "message": "本次未采集全市场概览"},
            },
        )
        (data_dir / "sample-evidence.json").write_text(json.dumps({
            "scope": "isolated real Tencent ETF samples; not daily/full universe",
            "startDate": start.isoformat(), "endDate": end.isoformat(), "rows": rows,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    if not (data_dir / "sample-evidence.json").is_file():
        raise SystemExit("Prepare and verify the isolated samples first")
    from app import create_app
    from flask import send_from_directory
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    application = create_app()
    provider = application.extensions["market_data_service"]._provider
    provider._assets = {key: provider._assets[key] for key in SYMBOLS}

    def no_upstream(*args, **kwargs):
        raise UpstreamUnavailableError("local browser acceptance permits validated cached samples only")

    provider._fetch_tencent = no_upstream
    dist = Path("apps/frontend/dist").resolve()
    if not (dist / "index.html").is_file():
        raise SystemExit("Build frontend first")

    @application.get("/")
    def index():
        return send_from_directory(dist, "index.html")

    @application.get("/assets/<path:name>")
    def assets(name):
        return send_from_directory(dist / "assets", name)

    application.run(host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
