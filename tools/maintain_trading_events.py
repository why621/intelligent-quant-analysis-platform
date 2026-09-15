"""Bounded official SSE daily evidence; unknown markets remain explicitly unconfirmed.

The official query uses YYYYMMDD and returns intervals intersecting the query.
Only the queried, completed session is added: an open interval is never extended
from an old snapshot. Resumption is established by actual validated later bars,
not absence from this list. Request/source failures cannot block other assets.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from time import monotonic
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from quant_platform.data.trading_events import TradingEvent, validate_events

from tools.collect_history_universe import atomic

SSE_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_PAGE = "https://www.sse.com.cn/disclosure/dealinstruc/suspension/"
MAX_BYTES = 2 * 1024 * 1024


def query_url(target):
    return (
        SSE_URL
        + "?"
        + urlencode(
            {
                "sqlId": "GW_PL_JYTS_TFPXX",
                "isPagination": "true",
                "pageHelp.pageSize": 1000,
                "pageHelp.pageNo": 1,
                "startStopDate": target.strftime("%Y%m%d"),
                "endStopDate": target.strftime("%Y%m%d"),
                "jsonCallBack": "callback",
            }
        )
    )


def fetch(url):
    # One request, no redirects/retry/environment proxies, bounded body AND duration.
    began = monotonic()
    with requests.Session() as session:
        session.trust_env = False
        with session.get(
            url,
            headers={"Referer": SSE_PAGE, "User-Agent": "Mozilla/5.0"},
            timeout=(5, 8),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise ValueError(f"http_{response.status_code}")
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > MAX_BYTES or monotonic() - began > 20:
                    raise ValueError("response_budget_exceeded")
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")


def parse_sse(raw, target, assets, *, reviewed_on=None):
    reviewed_on = reviewed_on or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    text = raw.strip()
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("response oversized")
    if text.startswith("callback(") and text.endswith(")"):
        text = text[len("callback(") : -1]
    value = json.loads(text)
    if not isinstance(value, dict) or value.get("success") in (False, "false"):
        raise ValueError("official service error")
    rows, page = value.get("result"), value.get("pageHelp")
    if (
        not isinstance(rows, list)
        or not isinstance(page, dict)
        or page.get("pageNo") != 1
        or page.get("pageCount") not in (0, 1)
        or type(page.get("total")) is not int
        or page["total"] != len(rows)
        or len(rows) > 1000
    ):
        raise ValueError("incomplete or changed official response")
    if value.get("sqlId") not in (None, "GW_PL_JYTS_TFPXX"):
        raise ValueError("wrong official dataset")
    events = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid row")
        # TR = trading; GB/CB = conversion and CP/GP = bond, not stock trading.
        symbol = row.get("productCode")
        if symbol not in assets or assets[symbol].asset_type != "stock":
            continue
        if assets[symbol].exchange != "SSE" or row.get("controlType") != "TR":
            continue
        start = datetime.strptime(row["startStopDate"], "%Y%m%d").date()
        end = datetime.strptime(row["endStopDate"], "%Y%m%d").date() if row["endStopDate"] else None
        if start > target or (end is not None and end < target):
            raise ValueError("official query returned out-of-date interval")
        full_day = row.get("stopTime") == "WH" or (
            row.get("type") == "LXTP" and row.get("stopTime") == ""
        )
        if not full_day:
            continue  # Intraday stops must not excuse missing daily prices.
        events.append(
            TradingEvent(
                f"stock:SSE:{symbol}",
                target,
                target,
                "suspension",
                query_url(target),
                reviewed_on,
                "自动核实官方全天交易停牌；仅确认本次查询交易日；不推算未来复牌日",
            )
        )
    return validate_events(events)


def merge_confirmed(previous, additions):
    # Preserve historical/manual provenance; only add uncovered calendar days.
    result = list(validate_events(previous))
    conflicts = []
    for event in additions:
        day = event.start
        while day <= event.end:
            old = next(
                (e for e in result if e.asset_id == event.asset_id and e.start <= day <= e.end),
                None,
            )
            if old and old.reason != event.reason:
                conflicts.append(event.asset_id)
            elif old is None:
                result.append(replace(event, start=day, end=day))
            day += timedelta(days=1)
    return validate_events(result), sorted(set(conflicts))


def maintain(output, target, previous, assets, *, request_budget=1, getter=fetch):
    events = validate_events(previous)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    report = {
        "asOfDate": target.isoformat(),
        "checkedAt": now.isoformat(),
        "state": "pending",
        "requests": 0,
        "sources": {},
        "conflicts": [],
    }
    report["sources"]["SZSE"] = {
        "state": "pending",
        "reason": "official_automatic_feed_not_verified",
    }
    report["sources"]["ETF"] = {
        "state": "pending",
        "reason": "trading_vs_subscription_feed_not_verified",
    }
    if target >= now.date():
        raise ValueError("cannot confirm uncompleted trading day")
    if request_budget >= 1:
        report["requests"] = 1
        try:
            raw = getter(query_url(target))
            additions = parse_sse(raw, target, assets, reviewed_on=now.date())
            events, conflicts = merge_confirmed(events, additions)
            report["conflicts"] = conflicts
            report["sources"]["SSE"] = {
                "state": "ready" if not conflicts else "pending",
                "sourceUrl": query_url(target),
                "responseSha256": sha256(raw.encode("utf-8")).hexdigest(),
                "confirmedCount": len(additions),
            }
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as exc:
            report["sources"]["SSE"] = {"state": "pending", "reason": type(exc).__name__}
    else:
        report["sources"]["SSE"] = {"state": "pending", "reason": "request_budget_reserved"}
    report["state"] = "partial" if report["sources"]["SSE"]["state"] == "ready" else "pending"
    output.mkdir(parents=True, exist_ok=True)
    atomic(output / "trading-events.json", [e.to_dict() for e in events])
    atomic(output / "event-maintenance.json", report)
    return report
