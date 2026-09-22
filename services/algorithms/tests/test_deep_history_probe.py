"""Deep-history capability probe (助教 long-window requirement).

These are the only tests allowed to touch the live upstream for long ranges, and
they fetch a bounded ~8-week window per case into memory. They never write the
SQLite cache, so running them cannot enlarge or re-anchor published history.
"""

from __future__ import annotations

from datetime import date

import pytest

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
    frame = _probe(date(2012, 1, 30), date(2012, 3, 30))
    assert not frame.empty, "510300 listing-era history is not reachable upstream"
