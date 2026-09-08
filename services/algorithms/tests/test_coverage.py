"""Synthetic bars only: no real constituent or suspension claims."""
from datetime import date

import pandas as pd
import pytest

from quant_platform.data.coverage import assess_history, expected_sessions

START, END = date(2026, 9, 3), date(2026, 9, 7)


def bars():
    return pd.DataFrame({"date": ["2026-09-03", "2026-09-04", "2026-09-07"],
                         "open": 10., "high": 12., "low": 9., "close": 11.,
                         "volume": 100., "amount": None})


def test_complete_dates_do_not_claim_complete_amount():
    result = assess_history(bars(), START, END)
    assert result["status"] == "complete"
    assert result["expectedSessions"] == result["observedSessions"] == 3
    assert result["amountMissingRows"] == 3
    assert result["gapReason"] is None


def test_endpoints_cannot_hide_interior_gaps_or_invent_suspension():
    result = assess_history(bars().iloc[[0, 2]], START, END)
    assert result["status"] == "gaps"
    assert result["missingSessions"] == ["2026-09-04"]
    assert result["gapReason"] == "unknown"


@pytest.mark.parametrize("column,value", [
    ("close", float("inf")), ("volume", -1), ("open", 0), ("low", 11),
    ("high", 10), ("date", "invalid"), ("date", "2026-09-05"),
    ("date", "2026-09-07"), ("date", "2026-09-03T12:00:00"),
    ("amount", -1), ("amount", "invalid"), ("close", None),
])
def test_invalid_not_silently_repaired(column, value):
    frame = bars().astype(object)
    frame.loc[0, column] = value
    assert assess_history(frame, START, END)["status"] == "invalid"


def test_unordered_duplicate_and_schema():
    assert assess_history(bars().iloc[::-1], START, END)["status"] == "invalid"
    result = assess_history(pd.concat([bars(), bars().iloc[:1]]), START, END)
    assert result["duplicateRows"] == 1
    assert result["status"] == "invalid"
    assert assess_history(bars().drop(columns="volume"), START, END)["status"] == "invalid"
    assert assess_history(pd.DataFrame(), START, END)["status"] == "empty"


@pytest.mark.parametrize("start,end", [
    (END, START), (date(2024, 1, 1), date(2024, 1, 2)),
    (date(2025, 1, 1), date(2026, 9, 7)), (date(2026, 9, 5), date(2026, 9, 6)),
])
def test_calendar_and_interval_fail_closed(start, end):
    with pytest.raises(ValueError):
        expected_sessions(start, end)
