"""Read-only probes of the actual adapter, with a hard deadline and no cache writes."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from quant_platform.data import upstream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["spot", "history"], required=True)
    parser.add_argument("--symbol", default="510300")
    parser.add_argument("--timeout", type=int, default=40)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180:
        parser.error("timeout must be between 1 and 180 seconds")
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    end = today - timedelta(days=max(0, today.weekday() - 4))
    payload = (
        {"date": today.isoformat()}
        if args.stage == "spot"
        else {
            "symbol": args.symbol,
            "start": (end - timedelta(days=4)).isoformat(),
            "end": end.isoformat(),
            "adjust": "qfq",
        }
    )
    try:
        result = upstream.run(args.stage, payload, timeout=args.timeout)
        if args.stage == "history":
            if not result:
                raise ValueError("no history rows returned")
            summary = {
                "rows": len(result),
                "firstDate": result[0]["date"],
                "lastDate": result[-1]["date"],
            }
        else:
            summary = result
        print(
            json.dumps(
                {"stage": args.stage, "status": "passed", "result": summary},
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"stage": args.stage, "status": "failed", "error": str(exc)}))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
