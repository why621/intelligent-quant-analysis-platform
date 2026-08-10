from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.data.storage import OHLCVStore


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": [1.0] * len(dates),
        "high": [2.0] * len(dates),
        "low": [0.5] * len(dates),
        "close": [1.5] * len(dates),
        "volume": [1000] * len(dates),
        "amount": [1500] * len(dates),
    })


class TestOHLCVStore:
    def test_save_load_roundtrip(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        df = _frame(["2025-01-01", "2025-01-02"])
        store.save("510300", df)

        loaded = store.load("510300")
        assert list(loaded["date"]) == list(df["date"])
        assert len(loaded) == 2
        assert set(loaded.columns) >= {"date", "open", "high", "low", "close", "volume", "amount"}

    def test_load_missing_returns_empty(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        assert store.load("510300").empty

    def test_save_deduplicates_within_frame(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        # 单次 save 内去重并按日期排序
        df = pd.concat([
            _frame(["2025-01-02", "2025-01-03"]),
            _frame(["2025-01-02"]),
        ], ignore_index=True)
        store.save("510300", df)

        loaded = store.load("510300")
        assert len(loaded) == 2  # 2025-01-02/03
        assert loaded["date"].is_monotonic_increasing

    def test_data_dir_created(self, tmp_path: Path):
        store = OHLCVStore(tmp_path / "nested" / "dir")
        store.save("510300", _frame(["2025-01-01"]))
        assert (tmp_path / "nested" / "dir" / "510300.csv").exists()


class TestHistoryCaching:
    def test_cache_hit_does_not_call_network(self, tmp_path: Path):
        """缓存覆盖请求范围时，不应调用腾讯接口。"""
        provider = AkShareMarketDataProvider(data_dir=tmp_path)
        provider._storage.save("510300", _frame([
            "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"
        ]))

        with patch("akshare.stock_zh_a_hist_tx") as mock_tx:
            df = provider.history("510300", date(2025, 1, 2), date(2025, 1, 6))
            mock_tx.assert_not_called()

        assert len(df) == 3  # 01-02, 01-03, 01-06
        assert df["date"].min() == pd.Timestamp("2025-01-02")
        assert df["date"].max() == pd.Timestamp("2025-01-06")

    def test_cache_miss_calls_network_and_saves(self, tmp_path: Path):
        """缓存不覆盖请求范围时，调用腾讯接口并更新缓存。"""
        provider = AkShareMarketDataProvider(data_dir=tmp_path)
        provider._storage.save("510300", _frame(["2025-01-01"]))

        new_data = _frame(["2025-01-02", "2025-01-03"])
        with patch("akshare.stock_zh_a_hist_tx", return_value=new_data) as mock_tx:
            df = provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))
            mock_tx.assert_called_once()

        assert len(df) == 2
        # 缓存已更新为合并后数据
        cached = provider._storage.load("510300")
        assert len(cached) == 3  # 01-01 + 01-02 + 01-03

    def test_no_cache_calls_network(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(data_dir=tmp_path)
        new_data = _frame(["2025-01-02", "2025-01-03"])
        with patch("akshare.stock_zh_a_hist_tx", return_value=new_data) as mock_tx:
            df = provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))
            mock_tx.assert_called_once()

        assert len(df) == 2
        assert provider._storage.has("510300")

    def test_network_failure_returns_cached_partial(self, tmp_path: Path):
        """网络失败时，返回缓存能覆盖到的部分。"""
        provider = AkShareMarketDataProvider(data_dir=tmp_path)
        provider._storage.save("510300", _frame(["2025-01-01", "2025-01-02"]))

        with patch("akshare.stock_zh_a_hist_tx", side_effect=Exception("timeout")):
            df = provider.history("510300", date(2025, 1, 1), date(2025, 1, 31))

        assert len(df) == 2  # 只有缓存里的两天
