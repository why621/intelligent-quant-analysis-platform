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


@pytest.fixture(autouse=True)
def _isolated_from_shipped_evidence(monkeypatch):
    """The repository ships a 2014—2024 table; these tests assert the *unverified* path."""
    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", "no-such-directory/absent.json")


def test_shipped_evidence_table_records_a_per_year_basis():
    document = json.loads(
        calendar.DEFAULT_EVIDENCE_PATH.read_text(encoding="utf-8")
    )
    table = calendar.parse_evidence(document)
    basis = calendar.parse_evidence_basis(document)
    assert set(range(2014, 2025)) <= set(table)
    assert basis == {year: "official-notice" for year in range(2014, 2025)}
    for entry in document["years"].values():
        assert entry["checkedOn"] and entry["verifiedAgainst"]
        assert entry["source"].startswith("https://www.sse.com.cn/")
    # 2020 needed two notices: the annual one closed Spring Festival through
    # 1月30日, and 上证公告〔2020〕6号 extended it to 2月2日, which is 2020-01-31.
    year_2020 = json.dumps(document["years"]["2020"], ensure_ascii=False)
    assert "上证公告〔2020〕6号" in year_2020
    assert "c_20200127_4991582.shtml" in year_2020
    # 2014's annual notice carries no 文号 of its own; the record says so and names
    # the 函 its four holiday announcements cite it by, rather than inventing one.
    year_2014 = json.dumps(document["years"]["2014"], ensure_ascii=False)
    assert "未标注文号" in year_2014
    assert "上证函〔2013〕269号" in year_2014
    assert "上证公告〔2014〕10号" in year_2014


def test_cross_validated_needs_an_audit_trail():
    incomplete = {
        "closures": [["01-01", "01-02"]],
        "source": SSE_2015["source"],
        "basis": "cross-validated",
    }
    for stripped in (
        incomplete,
        {**incomplete, "derivedFrom": "sina", "checkedOn": "2026-09-26"},
        {**incomplete, "derivedFrom": "sina", "verifiedAgainst": ["x"]},
        {
            **incomplete,
            "derivedFrom": "sina",
            "checkedOn": "not-a-date",
            "verifiedAgainst": ["x"],
        },
    ):
        with pytest.raises(CalendarUnavailableError):
            parse_evidence(_document({2015: stripped}))
    accepted = {
        **incomplete,
        "derivedFrom": "sina",
        "checkedOn": "2026-09-26",
        "verifiedAgainst": ["腾讯日线逐年双向一致"],
    }
    assert parse_evidence(_document({2015: accepted})) == {2015: [("01-01", "01-02")]}


def test_unknown_basis_is_refused():
    with pytest.raises(CalendarUnavailableError, match="basis"):
        parse_evidence(
            _document({2015: {**SSE_2015, "basis": "heard-it-from-a-friend"}})
        )


def test_a_partly_cited_official_year_is_refused():
    """Citing some checks but not all is the same silent gap as citing none."""
    for partial, missing in (
        ({"derivedFrom": "公告正文逐日展开"}, "checkedOn"),
        ({"verifiedAgainst": ["腾讯日线双向一致"]}, "derivedFrom"),
        ({"derivedFrom": "公告正文逐日展开", "checkedOn": "2026-09-26"}, "verifiedAgainst"),
    ):
        with pytest.raises(CalendarUnavailableError, match=missing):
            parse_evidence(_document({2015: {**SSE_2015, **partial}}))
    # A notice-only entry still passes: the audit trail is optional, not half-mandatory.
    notice_only = parse_evidence(_document({2015: SSE_2015}))
    assert notice_only == {2015: [("01-01", "01-02"), ("02-18", "02-23")]}


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


def test_preflight_reports_no_research_only_year_left_in_the_table(monkeypatch):
    """Every shipped year is now notice-backed; where the archive stops stays refused."""
    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", str(calendar.DEFAULT_EVIDENCE_PATH))
    report = preflight(date(2014, 1, 1), date(2026, 6, 30))
    assert report["ready"] is True and report["unverifiedYears"] == []
    assert report["crossValidatedYears"] == []
    assert calendar.closure_basis(2025) == "official-notice"
    assert calendar.closure_basis(2019) == "official-notice"
    assert calendar.closure_basis(2020) == "official-notice"
    assert calendar.closure_basis(2014) == "official-notice"
    # 2013 is where the exchange's own notice column runs out, not where we stopped
    # looking: the table's oldest year still has a hard edge.
    assert calendar.closure_basis(2013) is None
    assert unverified_years(date(2013, 1, 1), date(2014, 12, 31)) == [2013]


def _bars(first="2015-01-05", last="2015-01-06"):
    return pd.DataFrame(
        {
            "date": pd.to_datetime([first, last]),
            "open": [1.0, 1.1],
            "high": [1.1, 1.2],
            "low": [0.9, 1.0],
            "close": [1.05, 1.15],
            "volume": [100.0, 110.0],
            "amount": [105.0, 126.0],
        }
    )


def test_published_path_never_leans_on_a_cross_validated_calendar(tmp_path, monkeypatch):
    """The refusal keys on a year's basis, not on which year it is.

    The shipped table no longer carries a research-grade year, so the case builds
    one by downgrading 2020 in a copy: identical ranges, weaker evidence.
    """
    from quant_platform.data.akshare_provider import (
        AkShareMarketDataProvider,
        UpstreamUnavailableError,
    )

    document = json.loads(calendar.DEFAULT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    document["years"]["2020"]["basis"] = "cross-validated"
    downgraded = tmp_path / "calendar_closures.json"
    downgraded.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", str(downgraded))

    provider = AkShareMarketDataProvider(data_dir=tmp_path / "processed")
    provider._fetch_tencent = lambda *args, **kwargs: _bars("2020-02-03", "2020-02-04")

    with pytest.raises(UpstreamUnavailableError, match="仅限研究回填"):
        provider.history("510300", date(2020, 2, 3), date(2020, 2, 4))
    assert provider._load_history_cache("510300", "qfq").empty

    provider.allow_research_calendar = True
    assert len(provider.history("510300", date(2020, 2, 3), date(2020, 2, 4))) == 2


@pytest.mark.parametrize(
    "first,last",
    [
        ("2014-01-02", "2014-01-03"),
        ("2015-01-05", "2015-01-06"),
        ("2020-02-03", "2020-02-04"),
    ],
)
def test_published_path_accepts_an_officially_verified_history_year(
    tmp_path, monkeypatch, first, last
):
    """The point of the notice audit: these years are published-grade evidence."""
    from quant_platform.data.akshare_provider import AkShareMarketDataProvider

    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", str(calendar.DEFAULT_EVIDENCE_PATH))
    provider = AkShareMarketDataProvider(data_dir=tmp_path / "processed")
    provider._fetch_tencent = lambda *args, **kwargs: _bars(first, last)

    start = date.fromisoformat(first)
    assert calendar.closure_basis(start.year) == "official-notice"
    assert len(provider.history("510300", start, date.fromisoformat(last))) == 2


def test_backfill_opens_the_research_calendar(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("QUANT_CALENDAR_EVIDENCE", str(calendar.DEFAULT_EVIDENCE_PATH))
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path / "processed"))

    class _StubProvider:
        allow_research_calendar = False

        def __init__(self, data_dir=None):
            pass

        def history(self, symbol, start, end, adjust="qfq"):
            calls.append(self.allow_research_calendar)
            return _bars()

    monkeypatch.setattr(
        "quant_platform.data.akshare_provider.AkShareMarketDataProvider", _StubProvider
    )
    backfill(tmp_path / "research", ["510300"], date(2015, 1, 1), date(2015, 3, 1))
    assert calls == [True]


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
