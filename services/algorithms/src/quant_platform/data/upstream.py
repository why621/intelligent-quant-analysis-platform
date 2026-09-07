"""Bound complete SDK calls, including hidden requests; workers never open storage."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import date
from time import sleep

logger = logging.getLogger(__name__)


def run(stage: str, payload: dict, *, timeout: float, attempts: int = 1):
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "quant_platform.data.upstream_worker", stage],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=True,
            )
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            logger.warning(
                "upstream %s attempt %s failed: %s; stderr=%s",
                stage,
                attempt + 1,
                exc,
                getattr(exc, "stderr", ""),
            )
            if attempt + 1 == attempts:
                raise RuntimeError(f"{stage} failed after bounded attempts") from exc
            sleep(1)
    raise ValueError("attempts must be positive")


def main():
    stage = sys.argv[1]
    payload = json.load(sys.stdin)
    with redirect_stdout(sys.stderr):
        from quant_platform.data import market_fetch

        if stage == "spot":
            result = market_fetch.fetch_spot(date.fromisoformat(payload["date"]))
        elif stage == "northbound":
            result = market_fetch.fetch_northbound(date.fromisoformat(payload["date"]))
        elif stage == "index":
            result = market_fetch.fetch_index(
                payload["symbol"], payload["name"], date.fromisoformat(payload["date"])
            )
        elif stage == "history":
            from quant_platform.data.akshare_provider import AkShareMarketDataProvider

            provider = object.__new__(AkShareMarketDataProvider)
            frame = provider._fetch_tencent_inline(
                payload["symbol"],
                date.fromisoformat(payload["start"]),
                date.fromisoformat(payload["end"]),
                payload["adjust"],
            )
            result = json.loads(frame.to_json(orient="records", date_format="iso"))
        else:
            raise ValueError(f"unknown upstream stage: {stage}")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
