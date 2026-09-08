from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError
from quant_platform.data.storage import OHLCVStore


def bars(days, close=1.5):
    return pd.DataFrame({
        "date": pd.to_datetime(days), "open": close, "high": close + 1,
        "low": close - 1, "close": close, "volume": 100, "amount": 150,
    })


def provider_at(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
    provider._assets = {"510300": provider._assets["510300"]}
    return provider


def test_adjusted_extension_refetches_entire_cached_range(tmp_path):
    provider = provider_at(tmp_path)
    provider._storage.save("510300", bars(["2026-09-03", "2026-09-04"], 2.0))
    fresh = bars(["2026-09-03", "2026-09-04", "2026-09-07"], 1.0)
    with patch.object(provider, "_fetch_tencent", return_value=fresh) as fetch:
        provider.history("510300", date(2026, 9, 4), date(2026, 9, 7))
    fetch.assert_called_once_with("510300", date(2026, 9, 3), date(2026, 9, 7), "qfq")
    assert list(provider._storage.load("510300")["close"]) == [1.0, 1.0, 1.0]


def test_truncated_adjusted_response_cannot_pollute_cache(tmp_path):
    provider = provider_at(tmp_path)
    provider._storage.save("510300", bars(["2026-09-03", "2026-09-04"], 2.0))
    revision = provider.cache_revision()
    with (
        patch.object(provider, "_fetch_tencent", return_value=bars(["2026-09-07"], 1.0)),
        pytest.raises(UpstreamUnavailableError, match="coverage is incomplete"),
    ):
        provider.history("510300", date(2026, 9, 4), date(2026, 9, 7))
    assert provider.cache_revision() == revision
    assert list(provider._storage.load("510300")["close"]) == [2.0, 2.0]


def test_daily_update_corrects_old_adjusted_bars(tmp_path):
    provider = provider_at(tmp_path)
    provider._storage.save("510300", bars(["2026-09-04"], 2.0))
    with (
        patch("quant_platform.data.akshare_provider._today", return_value=date(2026, 9, 7)),
        patch.object(provider, "_fetch_tencent",
                     return_value=bars(["2026-09-04", "2026-09-07"], 1.0)) as fetch,
        patch.object(provider, "refresh_market_overview", return_value={}),
    ):
        status = provider.update_daily()
    fetch.assert_called_once_with("510300", date(2026, 9, 4), date(2026, 9, 7), "qfq")
    assert status.status == "ready"
    assert list(provider._storage.load("510300")["close"]) == [1.0, 1.0]


def test_empty_update_is_not_success(tmp_path):
    provider = provider_at(tmp_path)
    provider._storage.save("510300", bars(["2026-09-04"]))
    with (
        patch.object(provider, "_fetch_tencent", return_value=pd.DataFrame()),
        patch.object(provider, "refresh_market_overview", return_value={}),
    ):
        status = provider.update_daily()
    assert status.status == "stale"
    assert status.components["history"]["failedSymbols"] == ["510300"]


def test_revision_visible_to_other_process_store_and_invalid_write_is_atomic(tmp_path):
    first, second = OHLCVStore(tmp_path), OHLCVStore(tmp_path)
    old = second.revision()
    first.save("510300", bars(["2026-09-04"]))
    assert second.revision() != old
    revision = second.revision()
    invalid = bars(["2026-09-04"])
    invalid["close"] = float("inf")
    with pytest.raises(ValueError, match="non-finite"):
        first.save("510300", invalid)
    assert second.revision() == revision
    assert second.load("510300").iloc[0]["close"] == 1.5


def test_computation_budget_stops_calls_and_resets_context(tmp_path):
    provider = provider_at(tmp_path)
    with provider.computation_budget(0), patch.object(provider, "_fetch_tencent") as fetch:
        with pytest.raises(UpstreamUnavailableError, match="deadline"):
            provider.history("510300", date(2026, 9, 4), date(2026, 9, 7))
    fetch.assert_not_called()
    assert provider._remaining_budget() == 40.0


def test_oldest_asset_date_is_reported_and_mixed_freshness_is_stale(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
    provider._assets = {key: provider._assets[key] for key in ["510300", "510500"]}
    def fetch(symbol, *args):
        return bars(["2026-09-04" if symbol == "510300" else "2026-09-07"])
    with (
        patch("quant_platform.data.akshare_provider._today", return_value=date(2026, 9, 7)),
        patch.object(provider, "_fetch_tencent", side_effect=fetch),
        patch.object(provider, "refresh_market_overview", return_value={}),
    ):
        status = provider.update_daily()
    assert status.latest_trade_date == date(2026, 9, 4)
    assert status.status == "stale"
    assert status.components["history"]["failedSymbols"] == ["510300"]
