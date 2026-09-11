from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError
from quant_platform.data.calendar import CalendarUnavailableError, latest_session, sessions
from quant_platform.data.storage import _has_completed_weekday_since


def test_holiday_and_makeup_weekend_are_closed():
    assert sessions(date(2026, 2, 14), date(2026, 2, 23)) == []
    assert sessions(date(2026, 2, 28), date(2026, 3, 1)) == []
    assert latest_session(date(2026, 10, 7)) == date(2026, 9, 30)
    assert not _has_completed_weekday_since(date(2026, 9, 30), date(2026, 10, 8))
    assert _has_completed_weekday_since(date(2026, 9, 30), date(2026, 10, 9))


def test_unverified_year_is_explicit():
    with pytest.raises(CalendarUnavailableError, match="2027"):
        sessions(date(2027, 1, 1), date(2027, 1, 5))


def test_holiday_only_history_makes_no_network_call(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    with patch.object(provider, "_fetch_tencent") as fetch:
        assert provider.history("510300", date(2026, 10, 1), date(2026, 10, 7)).empty
    fetch.assert_not_called()


def test_interior_gap_is_not_a_cache_hit_and_failed_refresh_preserves_cache(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-02", "2026-09-04"]),
        "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100,
    })
    provider._storage.save("510300", frame)
    with (
        patch.object(provider, "_fetch_tencent", return_value=frame) as fetch,
        pytest.raises(UpstreamUnavailableError, match="missing sessions"),
    ):
        provider.history("510300", date(2026, 9, 2), date(2026, 9, 4))
    fetch.assert_called_once()
    assert len(provider._storage.load("510300")) == 2


def test_status_normalizes_utc_timestamp_before_date_comparison(tmp_path):
    import sqlite3

    from quant_platform.data.storage import DataStatusStore
    store = DataStatusStore(tmp_path)
    store.save("ready", date(2026, 9, 7), "test")
    with sqlite3.connect(tmp_path / "market_data.db") as connection:
        connection.execute(
            "UPDATE data_status_sync SET updated_at = '2026-09-06T17:00:00+00:00'"
        )
    with patch("quant_platform.data.storage._shanghai_today", return_value=date(2026, 9, 8)):
        status = store.load(1)
    assert status.status == "ready"
    assert status.updated_at.date() == date(2026, 9, 7)
