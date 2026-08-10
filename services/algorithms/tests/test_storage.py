from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import (
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.storage import OHLCVStore


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": [1.0] * len(dates),
            "high": [2.0] * len(dates),
            "low": [0.5] * len(dates),
            "close": [1.5] * len(dates),
            "volume": [1000] * len(dates),
            "amount": [1500] * len(dates),
        }
    )


def _tencent_frame(dates: list[str]) -> pd.DataFrame:
    """Match the documented Tencent schema: amount means volume in hands."""
    return pd.DataFrame(
        {
            "date": dates,
            "open": [1.0] * len(dates),
            "close": [1.5] * len(dates),
            "high": [2.0] * len(dates),
            "low": [0.5] * len(dates),
            "amount": [1234] * len(dates),
        }
    )


class TestOHLCVStore:
    def test_save_load_roundtrip(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = _frame(["2025-01-01", "2025-01-02"])
        store.save("510300", frame)

        loaded = store.load("510300")
        assert list(loaded["date"]) == list(frame["date"])
        assert len(loaded) == 2

    def test_save_deduplicates_and_sorts(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = pd.concat(
            [
                _frame(["2025-01-02", "2025-01-03"]),
                _frame(["2025-01-02"]),
            ],
            ignore_index=True,
        )
        store.save("510300", frame)

        loaded = store.load("510300")
        assert len(loaded) == 2
        assert loaded["date"].is_monotonic_increasing

    def test_missing_optional_amount_is_null(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = _frame(["2025-01-01"]).drop(columns="amount")
        store.save("510300", frame)
        assert pd.isna(store.load("510300").iloc[0]["amount"])

    def test_missing_required_column_is_rejected(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        with pytest.raises(ValueError, match="missing required"):
            store.save("510300", _frame(["2025-01-01"]).drop(columns="volume"))

    def test_invalid_symbol_is_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="six-digit"):
            OHLCVStore(tmp_path).load("../../secret")


class TestHistoryCaching:
    def test_cache_hit_does_not_call_network(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._storage.save(
            "510300", _frame(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-06"])
        )

        with patch("akshare.stock_zh_a_hist_tx") as mock_tencent:
            result = provider.history("510300", date(2025, 1, 2), date(2025, 1, 6))
        mock_tencent.assert_not_called()
        assert len(result) == 3

    def test_tencent_volume_is_mapped_to_contract(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with patch(
            "akshare.stock_zh_a_hist_tx",
            return_value=_tencent_frame(["2025-01-02", "2025-01-03"]),
        ):
            result = provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))

        assert result["volume"].tolist() == [1234, 1234]
        assert result["amount"].isna().all()
        assert len(provider._storage.load("510300")) == 2

    def test_network_failure_returns_cached_partial(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._storage.save("510300", _frame(["2025-01-01", "2025-01-02"]))

        with patch("akshare.stock_zh_a_hist_tx", side_effect=TimeoutError("timeout")):
            result = provider.history("510300", date(2025, 1, 1), date(2025, 1, 31))
        assert len(result) == 2

    def test_network_failure_without_cache_is_explicit(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with (
            patch("akshare.stock_zh_a_hist_tx", side_effect=TimeoutError("timeout")),
            pytest.raises(UpstreamUnavailableError),
        ):
            provider.history("510300", date(2025, 1, 1), date(2025, 1, 31))


class TestDailyUpdate:
    def test_old_cache_and_upstream_failure_is_stale(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}
        provider._storage.save("510300", _frame(["2025-01-02"]))

        with (
            patch.object(provider, "_fetch_tencent", side_effect=UpstreamUnavailableError()),
            patch.object(
                provider, "refresh_market_overview", side_effect=UpstreamUnavailableError()
            ),
        ):
            status = provider.update_daily()

        assert status.status == "stale"
        assert status.latest_trade_date == date(2025, 1, 2)
        assert "available=1/1" in (status.message or "")

    def test_no_cache_and_upstream_failure_is_failed(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}

        with (
            patch.object(provider, "_fetch_tencent", side_effect=UpstreamUnavailableError()),
            patch.object(
                provider, "refresh_market_overview", side_effect=UpstreamUnavailableError()
            ),
        ):
            status = provider.update_daily()
        assert status.status == "failed"

    def test_successful_refresh_is_ready(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}
        with (
            patch.object(provider, "_fetch_tencent", return_value=_frame(["2025-01-02"])),
            patch.object(provider, "refresh_market_overview", return_value={}),
        ):
            status = provider.update_daily()
        assert status.status == "ready"
        assert status.latest_trade_date == date(2025, 1, 2)


class TestMarketOverviewCache:
    def test_cache_hit_avoids_live_api(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        cached = {
            "tradeDate": "2025-01-02",
            "advancing": 1,
            "declining": 2,
            "unchanged": 3,
            "limitUp": 0,
            "limitDown": 0,
            "turnoverCny": 100.0,
            "northboundNetCny": None,
            "indices": [],
        }
        provider._overview_storage.save(cached)

        with patch.object(provider, "_fetch_market_overview") as live:
            assert provider.market_overview() == cached
        live.assert_not_called()

    def test_unavailable_historical_snapshot_is_not_fabricated(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with pytest.raises(ValueError, match="not available"):
            provider.market_overview(date(2025, 1, 2))

    def test_live_snapshot_uses_last_actual_trade_date(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        spot = pd.DataFrame({"涨跌幅": [1.0, -2.0, 0.0], "成交额": [10, 20, 30]})
        index_frame = pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03"],
                "close": [100.0, 102.0],
            }
        )
        northbound_frame = pd.DataFrame({"日期": ["2025-01-03"], "当日成交净买额": [1.5]})

        with (
            patch("akshare.stock_zh_a_spot_em", return_value=spot),
            patch("akshare.stock_hsgt_hist_em", return_value=northbound_frame),
            patch("akshare.stock_zh_index_daily", return_value=index_frame),
        ):
            result = provider._fetch_market_overview(date(2025, 1, 5))

        assert result["tradeDate"] == "2025-01-03"
        assert result["advancing"] == 1
        assert result["declining"] == 1
        assert result["unchanged"] == 1
        assert result["turnoverCny"] == 60.0
        assert result["indices"][0]["changePct"] == pytest.approx(2.0)
        assert result["northboundNetCny"] == 150_000_000.0
