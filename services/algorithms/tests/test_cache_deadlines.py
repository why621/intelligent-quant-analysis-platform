from datetime import date
from unittest.mock import patch

import pandas as pd

from quant_platform.data import upstream
from quant_platform.data.akshare_provider import AkShareMarketDataProvider


def frame():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-09-04"]),
            "open": [1],
            "high": [2],
            "low": [1],
            "close": [2],
            "volume": [100],
            "amount": [None],
        }
    )


def test_friday_cache_satisfies_sunday_end_date(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    provider._storage.save("510300", frame())
    with patch.object(upstream, "run") as run:
        result = provider.history("510300", date(2026, 9, 4), date(2026, 9, 6))
    run.assert_not_called()
    assert len(result) == 1


def test_weekend_only_range_does_not_query_upstream(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    with patch.object(upstream, "run") as run:
        assert provider.history("510300", date(2026, 9, 5), date(2026, 9, 6)).empty
    run.assert_not_called()


def test_new_overlap_replaces_old_cached_bar(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    provider._storage.save("510300", frame())
    corrected = frame()
    corrected["close"] = 1.5
    earlier = corrected.copy()
    earlier["date"] = pd.to_datetime(["2026-09-03"])
    corrected = pd.concat([earlier, corrected], ignore_index=True)
    with patch.object(provider, "_fetch_tencent", return_value=corrected):
        result = provider.history("510300", date(2026, 9, 3), date(2026, 9, 4))
    assert result.iloc[-1]["close"] == 1.5


def test_expired_batch_keeps_cache_and_records_skipped_assets(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
    provider._assets = {"510300": provider._assets["510300"]}
    provider._storage.save("510300", frame())
    with (
        patch("quant_platform.data.akshare_provider._HISTORY_BATCH_TIMEOUT_SECONDS", 0),
        patch("quant_platform.data.akshare_provider._today", return_value=date(2026, 9, 7)),
        patch.object(provider, "_fetch_tencent") as fetch,
        patch.object(provider, "refresh_market_overview", return_value={}),
    ):
        status = provider.update_daily()
    fetch.assert_not_called()
    assert status.components["history"]["status"] == "stale"
    assert status.components["history"]["failedSymbols"] == ["510300"]
    assert len(provider._storage.load("510300")) == 1
