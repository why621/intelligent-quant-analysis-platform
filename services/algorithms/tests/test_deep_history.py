"""Offline tests for the CR-052 evidence-backed calendar and deep backfill."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from quant_platform.data import calendar
from quant_platform.data.calendar import CalendarUnavailableError, is_session, parse_evidence
from quant_platform.data.deep_history import backfill, preflight, unverified_years


def _document(years):
    return {"schemaVersion": 1, "years": {str(key): value for key, value in years.items()}}


SSE_2015 = {
    "closures": [["01-01", "01-02"], ["02-18", "02-23"]],
    "source": "https://www.sse.com.cn/disclosure/dealinstruc/closed/c/example_2015.shtml",
}


def test_unverified_years_are_the_backfill_blocker():
    assert unverified_years(date(2015, 1, 1), date(2016, 1, 1)) == [2015, 2016]
    report = preflight(date(2015, 1, 5), date(2026, 6, 30))
    assert report["ready"] is False
    assert 2025 in report["verifiedYears"] and 2015 in report["unverifiedYears"]


def test_year_without_verified_closures_still_refuses_to_guess():
    with pytest.raises(CalendarUnavailableError, match="not verified for 2019"):
        is_session(date(2019, 5, 1))


def test_evidence_without_an_https_source_is_refused():
    with pytest.raises(CalendarUnavailableError, match="https"):
        parse_evidence(_document({2015: {"closures": [["01-01", "01-02"]], "source": ""}}))
    with pytest.raises(CalendarUnavailableError, match="https"):
        parse_evidence(
            _document(
                {
                    2015: {
                        "closures": [["01-01", "01-02"]],
                        "source": "http://example.com/notice",
                    }
                }
            )
        )


def test_evidence_cannot_override_hand_verified_years():
    with pytest.raises(CalendarUnavailableError, match="2025"):
        parse_evidence(_document({2025: SSE_2015}))


@pytest.mark.parametrize(
    "entry,reason",
    [
        ({"closures": [], "source": SSE_2015["source"]}, "缺少休市区间"),
        ({"closures": [["13-01", "13-02"]], "source": SSE_2015["source"]}, "非法"),
        ({"closures": [["05-04", "05-01"]], "source": SSE_2015["source"]}, "倒置"),
    ],
)
def test_malformed_closure_rows_are_refused(entry, reason):
    with pytest.raises(CalendarUnavailableError, match=reason):
        parse_evidence(_document({2015: entry}))


def test_verified_evidence_opens_the_year_without_touching_weekends(tmp_path, monkeypatch):
    path = tmp_path / "calendar_closures.json"
    path.write_text(json.dumps(_document({2015: SSE_2015})), encoding="utf-8")
    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", str(path))

    assert is_session(date(2015, 1, 1)) is False  # recorded closure
    assert is_session(date(2015, 1, 3)) is False  # Saturday is never a session
    assert is_session(date(2015, 1, 5)) is True
    assert unverified_years(date(2015, 1, 1), date(2015, 12, 31)) == []
    assert preflight(date(2015, 1, 1), date(2015, 12, 31))["ready"] is True
    # 2016 is still unverified: one cited year must not unlock the whole range.
    assert unverified_years(date(2015, 1, 1), date(2016, 12, 31)) == [2016]


def test_backfill_refuses_to_write_the_live_market_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path / "processed"))
    from quant_platform.data.akshare_provider import _default_data_dir

    with pytest.raises(ValueError, match="线上"):
        backfill(_default_data_dir(), ["510300"], date(2015, 1, 5), date(2015, 3, 6))


def test_backfill_needs_explicit_symbols_and_a_verified_calendar(tmp_path):
    with pytest.raises(ValueError, match="symbol"):
        backfill(tmp_path / "research", [], date(2015, 1, 5), date(2015, 3, 6))
    with pytest.raises(CalendarUnavailableError, match="2015"):
        backfill(tmp_path / "research", ["510300"], date(2015, 1, 5), date(2015, 3, 6))


def test_backfill_fetches_one_whole_range_per_symbol_and_reports_bars(
    tmp_path, monkeypatch
):
    calls = []
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2015-01-05", "2015-01-06"]),
            "open": [1.0, 1.1],
            "high": [1.1, 1.2],
            "low": [0.9, 1.0],
            "close": [1.05, 1.15],
            "volume": [100.0, 110.0],
            "amount": [105.0, 126.0],
        }
    )

    class _StubProvider:
        def __init__(self, data_dir=None):
            calls.append(("constructed", str(data_dir)))

        def history(self, symbol, start, end, adjust="qfq"):
            calls.append((symbol, start, end, adjust))
            return frame

    monkeypatch.setattr(calendar, "_evidence_closures", lambda: {2015: []})
    monkeypatch.setattr(
        "quant_platform.data.akshare_provider.AkShareMarketDataProvider", _StubProvider
    )

    rows = backfill(tmp_path / "research", ["510300", "600000"], date(2015, 1, 1), date(2015, 3, 1))

    assert [row["symbol"] for row in rows] == ["510300", "600000"]
    assert rows[0]["bars"] == 2
    assert rows[0]["firstDate"] == "2015-01-05" and rows[0]["lastDate"] == "2015-01-06"
    # qfq re-anchors the whole series, so each symbol gets exactly one full call.
    fetched = [call for call in calls if call[0] != "constructed"]
    assert len(fetched) == 2
    assert all(call[1] == date(2015, 1, 1) and call[3] == "qfq" for call in fetched)
