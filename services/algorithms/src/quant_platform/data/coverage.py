"""Pure candidate-history checks; never a published-data or suspension assertion."""

from __future__ import annotations

import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd

from quant_platform.data.calendar import sessions


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def expected_sessions(start: date, end: date) -> list[date]:
    if start > end or (end - start).days > 366:
        raise ValueError("coverage requires an ordered interval of at most 366 days")
    expected = sessions(start, end)
    if not expected:
        raise ValueError("coverage interval has no trading sessions")
    return expected


def assess_history(
    frame: pd.DataFrame, start: date, end: date, *, events=None, asset_id=None
) -> dict:
    """Check each date, not just endpoints; unknown gaps remain unexplained.

    Input is adapter-normalized daily bars. Does not verify SDK raw overlap,
    corporate actions, legal access, or economic correctness of adjustment.
    """
    expected = expected_sessions(start, end)
    expected_set = set(expected)
    required = ["date", "open", "high", "low", "close", "volume"]
    missing_columns = [key for key in required if key not in frame]
    rows = len(frame)
    dates = pd.to_datetime(
        frame.get("date", pd.Series(index=frame.index, dtype=object)),
        errors="coerce",
        format="mixed",
    )
    try:
        if dates.dt.tz is not None:
            raise ValueError("daily dates must be timezone-naive")
        date_invalid = dates.isna() | (dates != dates.dt.normalize())
    except AttributeError as exc:
        raise ValueError("daily dates have mixed timezones or invalid types") from exc
    valid_dates = dates[~date_invalid]
    observed = set(valid_dates.dt.date)
    duplicates = int(valid_dates.duplicated().sum())
    unexpected = sorted(observed - expected_set)
    missing = sorted(expected_set - observed)
    numeric = frame.reindex(columns=required[1:]).apply(pd.to_numeric, errors="coerce")
    invalid = ~np.isfinite(numeric).all(axis=1)
    prices = numeric[["open", "high", "low", "close"]]
    invalid |= (prices <= 0).any(axis=1) | (numeric["volume"] < 0)
    invalid |= numeric["high"] < prices.max(axis=1)
    invalid |= numeric["low"] > prices.min(axis=1)
    amounts = frame.get("amount", pd.Series(np.nan, index=frame.index))
    numeric_amount = pd.to_numeric(amounts, errors="coerce")
    invalid |= amounts.notna() & (~np.isfinite(numeric_amount) | (numeric_amount < 0))
    invalid |= date_invalid
    invalid_count = int(invalid.sum())
    ordered = bool(valid_dates.is_monotonic_increasing)
    if not rows:
        status = "empty"
    elif missing_columns or invalid_count or duplicates or unexpected or not ordered:
        status = "invalid"
    elif missing:
        status = "gaps"
    else:
        status = "complete"
    result = {
        "status": status,
        "rowCount": rows,
        "expectedSessions": len(expected),
        "observedSessions": len(observed & expected_set),
        "firstDate": min(observed).isoformat() if observed else None,
        "lastDate": max(observed).isoformat() if observed else None,
        "missingSessions": [day.isoformat() for day in missing],
        "unexpectedSessions": [day.isoformat() for day in unexpected],
        "gapReason": "unknown" if missing else None,
        "duplicateRows": duplicates,
        "invalidRows": invalid_count,
        "missingColumns": missing_columns,
        "ordered": ordered,
        "amountMissingRows": int(amounts.isna().sum()),
    }

    if events is not None:
        from quant_platform.data.trading_events import classify_sessions

        if not asset_id:
            raise ValueError("event coverage requires explicit asset_id")
        classified = classify_sessions(events, asset_id, expected)
        explained = [
            day
            for day in missing
            if day in classified and classified[day].reason != "identity_change"
        ]
        identity = [
            day
            for day in missing
            if day in classified and classified[day].reason == "identity_change"
        ]
        unknown = sorted(set(missing) - set(explained) - set(identity))
        contradictory = [
            day
            for day in observed
            if day in classified and classified[day].reason != "identity_change"
        ]
        result.update(
            explainedMissingSessions=[
                {
                    "date": day.isoformat(),
                    "reason": classified[day].reason,
                    "evidenceId": classified[day].evidence_id,
                }
                for day in explained
            ],
            unknownMissingSessions=[day.isoformat() for day in unknown],
            blockedIdentitySessions=[day.isoformat() for day in identity],
            tradableSessions=len(expected)
            - sum(event.reason != "identity_change" for event in classified.values()),
            contradictorySessions=[day.isoformat() for day in sorted(contradictory)],
        )
        if contradictory:
            result["status"] = "invalid"
        elif status == "gaps" and not unknown and not identity:
            result["status"] = "complete_with_exceptions"
        result["gapReason"] = (
            "unknown"
            if unknown
            else "identity_change"
            if identity
            else "documented"
            if explained
            else None
        )
    return result
