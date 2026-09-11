"""Isolated bounded SDK probe. This worker never constructs or writes a data store."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime, timedelta
from time import monotonic
from unittest.mock import patch
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests

from quant_platform.data.coverage import expected_sessions

ALLOWED_HOSTS = {"web.ifzq.gtimg.cn", "proxy.finance.qq.com"}
MAX_REQUESTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@contextmanager
def bounded_requests(trace: list):
    """Instrument only this short-lived worker; no global application monkeypatch."""
    original = requests.Session.request

    def request(session, method, url, **kwargs):
        target = urlsplit(url)
        if (
            method.upper() != "GET"
            or target.scheme != "https"
            or target.hostname not in ALLOWED_HOSTS
            or target.port not in (None, 443)
            or target.username
            or target.password
        ):
            raise ValueError("probe request outside approved HTTPS hosts")
        if len(trace) >= MAX_REQUESTS:
            raise ValueError("probe HTTP request budget exhausted")
        session.trust_env = False
        kwargs.update(timeout=(5, 10), allow_redirects=False, stream=True, proxies={})
        event = {"host": target.hostname, "path": target.path, "status": None, "error": None}
        trace.append(event)
        started = monotonic()
        try:
            with original(session, method, url, **kwargs) as response:
                event["status"] = response.status_code
                if response.status_code != 200:
                    raise ValueError(f"probe HTTP status {response.status_code}")
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ValueError("probe response oversized")
                    chunks.append(chunk)
                # SDK consumes .text after this call. Bound bytes before its decoding.
                response._content = b"".join(chunks)
                response._content_consumed = True
                return response
        except Exception as exc:
            event["error"] = type(exc).__name__
            raise
        finally:
            event["elapsedSeconds"] = round(monotonic() - started, 3)

    with patch.object(requests.Session, "request", request):
        yield


def probe(payload: dict) -> dict:
    from quant_platform.data.akshare_provider import (
        _DEFAULT_UNIVERSE,
        AkShareMarketDataProvider,
        ak,
    )

    etfs = {a["symbol"] for a in _DEFAULT_UNIVERSE if a["asset_type"] == "etf"}
    symbol = payload["symbol"]
    if (
        not isinstance(symbol, str)
        or len(symbol) != 6
        or not symbol.isascii()
        or not symbol.isdigit()
        or (symbol[0] not in "036" and symbol not in etfs)
    ):
        raise ValueError("probe accepts only SSE/SZSE stocks or explicit legacy ETF whitelist")
    start, end = date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"])
    expected_sessions(start, end)
    if end > datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1):
        raise ValueError("probe cannot include an uncompleted day")
    if ak.__version__ != "1.18.94":
        raise ValueError("revalidate history probe for changed SDK")
    trace = []
    result = {
        "symbol": symbol,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "adjust": "qfq",
        "source": "Tencent",
        "sdkVersion": ak.__version__,
        "normalizationVersion": "tx-1.18.94-project-v1",
        "retrievedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "records": [],
        "error": None,
        "httpTrace": trace,
    }
    try:
        with bounded_requests(trace):
            provider = object.__new__(AkShareMarketDataProvider)
            frame = provider._fetch_tencent_inline(symbol, start, end, "qfq")
        result["records"] = json.loads(frame.to_json(orient="records", date_format="iso"))
    except Exception as exc:
        # Exception class chain, not raw URLs/headers or potentially credential-bearing text.
        causes = []
        while exc is not None and len(causes) < 5:
            causes.append(type(exc).__name__)
            exc = exc.__cause__
        result["error"] = ":".join(causes)
    return result


def main():
    payload = json.load(sys.stdin)
    with redirect_stdout(sys.stderr):
        result = probe(payload)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
