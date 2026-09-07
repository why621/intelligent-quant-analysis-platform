"""Validated Eastmoney pagination and date-aligned optional indicators.

Endpoint/filter follow AkShare stock_zh_a_spot_em. Field f124 is the upstream
update timestamp, not a date inferred from an unrelated index. No endpoint failover.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from time import sleep
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd
import requests

from quant_platform.data.calendar import latest_session

SHANGHAI = ZoneInfo("Asia/Shanghai")
SPOT_URL = "https://82.push2.eastmoney.com/api/qt/clist/get"
SPOT_PARAMS = {
    "pn": "1",
    "pz": "100",
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
    "fields": "f3,f6,f12,f13,f124",
}


def _number(value):
    if value in (None, "", "-"):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite upstream number")
    return result


def _page(session, params):
    for attempt in range(2):
        try:
            response = session.get(SPOT_URL, params=params, timeout=(5, 10))
            response.raise_for_status()
            payload = response.json()
            if payload.get("rc") != 0 or not isinstance(payload.get("data"), dict):
                raise ValueError("invalid Eastmoney envelope")
            return payload["data"]
        except (requests.RequestException, ValueError):
            if attempt:
                raise
            sleep(1)
    raise AssertionError("unreachable")


def fetch_spot(requested_date: date):
    rows = []
    seen = set()
    total = None
    with requests.Session() as session:
        for page in range(1, 101):
            data = _page(session, {**SPOT_PARAMS, "pn": str(page)})
            count, batch = data.get("total"), data.get("diff")
            if type(count) is not int or not 0 < count <= 10000:
                raise ValueError("invalid market universe size")
            if total is not None and count != total:
                raise ValueError("market universe changed during pagination")
            total = count
            if not isinstance(batch, list) or not batch or len(batch) > 100:
                raise ValueError("missing/invalid market page")
            for row in batch:
                symbol = row.get("f12")
                if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
                    raise ValueError("non-stock code in market page")
                if row.get("f13") not in (0, 1):
                    raise ValueError("invalid exchange in market page")
                if symbol in seen:
                    raise ValueError("duplicate stock/page in market snapshot")
                seen.add(symbol)
                rows.append(row)
            if len(rows) >= total:
                break
            sleep(0.5)
    if len(rows) != total:
        raise ValueError("incomplete market snapshot")
    return summarise(rows, requested_date)


def summarise(rows, requested_date: date):
    changes, amounts, dates = [], [], set()
    for row in rows:
        timestamp = _number(row.get("f124"))
        if timestamp is None:
            raise ValueError("market snapshot has no verified trade date")
        observed = datetime.fromtimestamp(timestamp, SHANGHAI).date()
        if observed != latest_session(requested_date):
            raise ValueError("future or obsolete market timestamp")
        dates.add(observed)
        changes.append(_number(row.get("f3")))
        amount = _number(row.get("f6"))
        if amount is not None and amount < 0:
            raise ValueError("negative turnover")
        amounts.append(amount)
    if len(dates) != 1:
        raise ValueError("mixed market snapshot dates")
    valid = [value for value in changes if value is not None]
    if not valid:
        raise ValueError("market snapshot has no valid price changes")
    unavailable = ["limitUp", "limitDown"]
    if any(value is None for value in amounts):
        unavailable.append("turnoverCny")
    return {
        "tradeDate": dates.pop().isoformat(),
        "advancing": sum(value > 0 for value in valid),
        "declining": sum(value < 0 for value in valid),
        "unchanged": sum(value == 0 for value in valid),
        "limitUp": None,
        "limitDown": None,
        "turnoverCny": None if "turnoverCny" in unavailable else sum(amounts),
        "northboundNetCny": None,
        "indices": [],
        "unavailableMetrics": unavailable,
        "coverage": {"total": len(rows), "priced": len(valid)},
    }


def fetch_northbound(trade_date: date):
    frame = ak.stock_hsgt_hist_em(symbol="北向资金")
    dates = pd.to_datetime(frame["日期"], errors="coerce").dt.date
    values = frame.loc[dates == trade_date, "当日成交净买额"]
    if len(values) != 1:
        return None
    value = _number(values.iloc[0])
    return None if value is None else value * 100_000_000


def fetch_index(symbol: str, name: str, trade_date: date):
    prefix = "sh" if symbol.startswith("0") else "sz"
    frame = ak.stock_zh_index_daily(symbol=f"{prefix}{symbol}")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame[frame["date"] <= pd.Timestamp(trade_date)].sort_values("date")
    if len(frame) < 2 or frame.iloc[-1]["date"].date() != trade_date:
        return None
    latest, previous = _number(frame.iloc[-1]["close"]), _number(frame.iloc[-2]["close"])
    if latest is None or previous is None or latest <= 0 or previous <= 0:
        return None
    return {
        "symbol": symbol,
        "name": name,
        "close": latest,
        "changePct": (latest / previous - 1) * 100,
    }
