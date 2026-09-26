"""Deep-history capability probe (助教 long-window requirement).

These are the only tests allowed to touch the live upstream for long ranges, and
they fetch a bounded ~8-week window per case into memory. They never write the
SQLite cache, so running them cannot enlarge or re-anchor published history.

``test_shipped_calendar_still_matches_both_independent_observations`` re-runs the
CR-053 audit behind ``data/calendar_closures.json``: if either upstream moves, the
cross-validated years stop being admissible evidence and the run fails loudly.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_platform.data import calendar
from quant_platform.data.akshare_provider import AkShareMarketDataProvider

pytestmark = pytest.mark.network

PROBES = [
    ("2015-bull-crash", date(2015, 6, 1), date(2015, 8, 31)),
    ("2018-bear", date(2018, 10, 8), date(2018, 12, 28)),
    ("2020-shock", date(2020, 2, 3), date(2020, 4, 30)),
]


def _probe(start: date, end: date):
    provider = object.__new__(AkShareMarketDataProvider)
    return provider._fetch_tencent_inline("510300", start, end, "qfq")


@pytest.mark.parametrize("label,start,end", PROBES, ids=[probe[0] for probe in PROBES])
def test_upstream_serves_long_range_daily_bars(label, start, end):
    frame = _probe(start, end)
    assert not frame.empty, f"{label}: upstream returned no bars for {start}..{end}"
    days = list(frame["date"].dt.date)
    assert days == sorted(days) and len(set(days)) == len(days)
    assert days[0] >= start and days[-1] <= end
    # A ~3 month window must contain at least one month of sessions.
    assert len(days) >= 20, f"{label}: only {len(days)} bars, range looks truncated"
    assert (frame["high"] >= frame["low"]).all()
    assert (frame[["open", "high", "low", "close"]] > 0).all().all()


def test_upstream_reaches_pre_2015_history():
    # 510300 listed 2012-05-28; a window before that is correctly empty, so the
    # probe must sit after listing to test upstream reach at all.
    frame = _probe(date(2012, 6, 1), date(2012, 8, 31))
    assert not frame.empty, "510300 listing-era history is not reachable upstream"
    assert frame["date"].dt.date.min() >= date(2012, 5, 28)


def _weekday_closures(session_set: set[date], year: int) -> set[date]:
    day, out = date(year, 1, 1), set()
    while day.year == year:
        if day.weekday() < 5 and day not in session_set:
            out.add(day)
        day += timedelta(days=1)
    return out


def _official_weekday_closures(year: int, ranges) -> set[date]:
    weekdays = _weekday_closures(set(), year)
    return {
        day
        for day in weekdays
        if any(start <= day.strftime("%m-%d") <= end for start, end in ranges)
    }


def test_shipped_calendar_still_matches_both_independent_observations():
    import json

    import pandas as pd

    document = json.loads(calendar.DEFAULT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    table = calendar.parse_evidence(document)

    import akshare as ak

    sina = set(pd.to_datetime(ak.tool_trade_date_hist_sina()["trade_date"]).dt.date)
    # Observation 1: the years we checked against official SSE notices by hand.
    for year, official in calendar._CLOSURES.items():
        assert _weekday_closures(sina, year) == _official_weekday_closures(year, official), (
            f"{year} 与官方公告口径已不一致"
        )

    # Observation 2: bars from the transport the backfill itself uses.
    provider = object.__new__(AkShareMarketDataProvider)
    bars = provider._fetch_tencent_inline("510300", date(2015, 1, 1), date(2024, 12, 31), "qfq")
    assert not bars.empty, "腾讯通道无 2015—2024 日线，证据表失去观测支撑"
    traded = {day.date() for day in pd.to_datetime(bars["date"])}
    assert not sorted(traded - sina), "真实K线出现在候选休市日，候选日历有误"
    for year in sorted(table):
        assert _weekday_closures(sina, year) == _weekday_closures(traded, year), (
            f"{year} 逐年双向比对失败"
        )
