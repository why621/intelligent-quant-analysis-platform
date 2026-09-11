"""Bounded read-only source probes. Linux only; no application/cache writes.

Run locally with the project venv or stream into the backend container with
python -u -. All output goes to stdout; no credentials are printed.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import platform
import signal
import time
from datetime import datetime
from urllib.parse import urlsplit

import akshare as ak
import pandas as pd
import requests

START, END = "20260901", "20260907"
MAX_REQUESTS = 24
request_count = 0
last_request = 0.0
case_requests = 0
original_request = requests.sessions.Session.request


def emit(event, **values):
    print(json.dumps({"utc": datetime.now().astimezone().isoformat(),
                      "event": event, **values}, ensure_ascii=False,
                     allow_nan=False), flush=True)


def deadline(_signum, _frame):
    raise TimeoutError("case hard deadline 45 seconds")


def bounded_request(session, method, url, **kwargs):
    global request_count, last_request, case_requests
    if request_count >= MAX_REQUESTS or case_requests >= 4:
        raise RuntimeError("read-only request budget exhausted")
    time.sleep(max(0, 2.0 - (time.monotonic() - last_request)))
    session.trust_env = False
    kwargs["timeout"] = (5, 8)
    kwargs["allow_redirects"] = False
    request_count += 1
    case_requests += 1
    last_request = time.monotonic()
    parsed = urlsplit(url)
    emit("request", number=request_count, host=parsed.hostname, path=parsed.path)
    response = original_request(session, method, url, **kwargs)
    emit("http", number=request_count, status=response.status_code)
    response.raise_for_status()
    if 300 <= response.status_code < 400:
        raise RuntimeError("redirect not followed by bounded probe")
    return response


def summarize(frame):
    if frame is None or frame.empty:
        raise ValueError("empty frame")
    date_column = "日期" if "日期" in frame else "date"
    dates = pd.to_datetime(frame[date_column], errors="raise")
    summary = {"rows": len(frame), "first": str(dates.min().date()),
               "last": str(dates.max().date()), "columns": list(frame.columns),
               "unique_dates": bool(dates.is_unique),
               "ascending": bool(dates.is_monotonic_increasing)}
    aliases = {"open": "开盘", "close": "收盘", "high": "最高", "low": "最低",
               "volume": "成交量", "amount": "成交额"}
    records = []
    for index, row in frame.iterrows():
        record = {"date": str(pd.to_datetime(row[date_column]).date())}
        for name, chinese in aliases.items():
            column = name if name in frame else chinese
            if column in frame:
                value = pd.to_numeric(row[column], errors="coerce")
                record[name] = None if pd.isna(value) else float(value)
        records.append(record)
    summary["records"] = records
    return summary


def run_case(name, operation):
    global case_requests
    case_requests = 0
    began = time.monotonic()
    signal.alarm(45)
    try:
        result = operation()
        emit("result", name=name, outcome="passed",
             seconds=round(time.monotonic() - began, 3), result=result)
        return result
    except Exception as exc:  # noqa: BLE001 - isolate arbitrary SDK failures per probe
        # Exception type is enough; URLs in exception strings can contain tokens.
        emit("result", name=name, outcome="failed",
             seconds=round(time.monotonic() - began, 3),
             error_type=type(exc).__name__)
        return None
    finally:
        signal.alarm(0)


def constituents():
    frame = ak.index_stock_cons_csindex(symbol="000300")
    codes = frame["成分券代码"].astype(str).str.zfill(6)
    if len(frame) != 300 or not codes.is_unique:
        raise ValueError("constituent coverage is not 300 unique securities")
    if set(frame["指数代码"].astype(str).str.zfill(6)) != {"000300"}:
        raise ValueError("wrong index")
    dates = sorted(set(frame["日期"].astype(str)))
    if len(dates) != 1 or dates[0] == "NaT" or dates[0] > "2026-09-07":
        raise ValueError("invalid constituent snapshot date")
    selected = []
    for prefix in ("6", "0"):
        matches = frame.loc[codes.str.startswith(prefix)].sort_values("成分券代码")
        if matches.empty:
            raise ValueError("missing exchange sample")
        row = matches.iloc[0]
        selected.append({"code": str(row["成分券代码"]).zfill(6),
                         "name": str(row["成分券名称"]),
                         "exchange": str(row["交易所"])})
    return {"count": len(frame), "snapshot_date": dates[0], "selected": selected,
            "history_membership_verified": False}


def direct_index():
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {"secid": "1.000300", "ut": "7eea3edcaed734bea9cbfc24409ed989",
              "fields1": "f1,f2,f3,f4,f5,f6",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
              "klt": "101", "fqt": "0", "beg": START, "end": END}
    data = requests.get(url, params=params).json().get("data")
    if not data or data.get("code") != "000300" or data.get("name") != "沪深300":
        raise ValueError("index identity could not be verified")
    frame = pd.DataFrame([bar.split(",") for bar in data["klines"]],
                         columns=["date", "open", "close", "high", "low",
                                  "volume", "amount", "amplitude", "change_pct",
                                  "change", "turnover"])
    return {"identity": {"code": data["code"], "name": data["name"]},
            **summarize(frame)}


def main():
    requests.sessions.Session.request = bounded_request
    signal.signal(signal.SIGALRM, deadline)
    emit("environment", python=platform.python_version(), akshare=ak.__version__,
         start=START, end=END, request_budget=MAX_REQUESTS,
         cache_writes=False, proxy_environment_ignored=True,
         source_hashes={name: hashlib.sha256(inspect.getsource(getattr(ak, name)).encode()).hexdigest()
                        for name in ("stock_zh_a_hist", "stock_zh_a_hist_tx", "index_zh_a_hist")})
    members = run_case("csi300_constituents", constituents)
    run_case("eastmoney_index_sdk", lambda: summarize(ak.index_zh_a_hist(
        symbol="000300", period="daily", start_date=START, end_date=END)))
    run_case("eastmoney_index_direct", direct_index)
    if members:
        for member in members["selected"]:
            code = member["code"]
            run_case("eastmoney_stock_" + code, lambda code=code: summarize(
                ak.stock_zh_a_hist(symbol=code, start_date=START, end_date=END,
                                  adjust="qfq", timeout=8)))
            symbol = ("sh" if code.startswith("6") else "sz") + code
            run_case("tencent_stock_" + code, lambda symbol=symbol: summarize(
                ak.stock_zh_a_hist_tx(symbol=symbol, start_date=START,
                                     end_date=END, adjust="qfq", timeout=8)))
    else:
        emit("skipped", reason="stock samples require validated constituent snapshot")
    emit("completed", requests=request_count, cache_writes=False)


if __name__ == "__main__":
    main()
