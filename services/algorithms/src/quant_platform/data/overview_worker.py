"""Disposable read-only worker; the parent enforces a hard wall-clock timeout."""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from datetime import date


def main() -> None:
    # Keep library progress output away from the JSON protocol. This worker never
    # opens storage: a timed-out/failed refresh cannot replace a valid snapshot.
    with redirect_stdout(sys.stderr):
        from quant_platform.data.akshare_provider import AkShareMarketDataProvider

        overview = AkShareMarketDataProvider._fetch_market_overview(
            date.fromisoformat(sys.argv[1])
        )
    print(json.dumps(overview, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
