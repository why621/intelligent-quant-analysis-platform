"""Command-line entry point for the server's once-daily data refresh."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime

from quant_platform.data.akshare_provider import AkShareMarketDataProvider


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialise {type(value).__name__}")


def main() -> int:
    """Refresh local caches and return a cron-friendly process status."""
    status = AkShareMarketDataProvider().update_daily()
    print(json.dumps(asdict(status), ensure_ascii=False, default=_json_default))
    if status.status == "ready":
        return 0
    if status.status == "stale":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
