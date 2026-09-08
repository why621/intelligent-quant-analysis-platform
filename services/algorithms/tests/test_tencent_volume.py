from datetime import date

import akshare as ak
import pandas as pd
import pytest

from quant_platform.data.akshare_provider import (
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.storage import OHLCVStore


def frame(dates=("2026-09-07",), volume=1087276):
    return pd.DataFrame({"date": pd.to_datetime(dates), "open": 11.87,
                         "close": 11.7, "high": 11.88, "low": 11.65,
                         "volume": volume, "amount": 1275606300})


@pytest.mark.parametrize("symbol,factor", [("000001", 100), ("000333", 100),
                                          ("600000", 1), ("510300", 1)])
def test_current_sdk_units(monkeypatch, symbol, factor):
    raw = frame()
    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", lambda **kwargs: raw)
    monkeypatch.setattr(ak, "__version__", "1.18.94")
    provider = object.__new__(AkShareMarketDataProvider)
    result = provider._fetch_tencent_inline(symbol, date(2026, 9, 7), date(2026, 9, 7), "qfq")
    assert result.volume.iloc[0] == 1087276 * factor
    assert raw.volume.iloc[0] == 1087276
    assert result.amount.iloc[0] == 1275606300


def test_unknown_sdk_fails_closed(monkeypatch):
    monkeypatch.setattr(ak, "stock_zh_a_hist_tx", lambda **kwargs: frame())
    monkeypatch.setattr(ak, "__version__", "future")
    provider = object.__new__(AkShareMarketDataProvider)
    with pytest.raises(UpstreamUnavailableError, match="revalidate"):
        provider._fetch_tencent_inline("000001", date(2026, 9, 7), date(2026, 9, 7), "qfq")


def test_legacy_cache_refused_without_overwriting(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    provider._storage.save("000001", frame())
    with pytest.raises(UpstreamUnavailableError, match="volume schema"):
        provider.history("000001", date(2026, 9, 7), date(2026, 9, 7))
    assert provider._storage.load("000001").volume.iloc[0] == 1087276


def test_versioned_cache_survives_restart_without_repeated_factor(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    provider._save_history_cache("000001", frame(volume=108727600))
    restarted = AkShareMarketDataProvider(tmp_path)
    result = restarted.history("000001", date(2026, 9, 7), date(2026, 9, 7))
    assert result.volume.iloc[0] == 108727600


def test_partial_migration_refused_atomically(tmp_path):
    store = OHLCVStore(tmp_path)
    store.save("000001", frame(("2026-09-04", "2026-09-07")))
    revision = store.revision()
    with pytest.raises(ValueError, match="every cached date"):
        store.save("000001", frame(volume=108727600), volume_version="v1")
    assert store.revision() == revision
    assert store.load("000001").volume.tolist() == [1087276, 1087276]


def test_unversioned_write_invalidates_marker(tmp_path):
    store = OHLCVStore(tmp_path)
    store.save("000001", frame(), volume_version="v1")
    store.save("000001", frame())
    with pytest.raises(ValueError, match="volume schema"):
        store.load("000001", required_volume_version="v1")
