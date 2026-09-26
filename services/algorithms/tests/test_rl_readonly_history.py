"""Training reads an existing research cache without acquisition or migration."""
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError
from quant_platform.data.storage import OHLCVStore
from quant_platform.rl.errors import RLInvalidSplit
from quant_platform.rl.train import _training_provider


def test_missing_root_is_not_created(tmp_path):
    root = tmp_path / "missing"
    provider = _training_provider(None, root)
    provider._fetch_tencent = Mock(side_effect=AssertionError("network forbidden"))
    with pytest.raises(UpstreamUnavailableError, match="cache missing"):
        provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))
    provider._fetch_tencent.assert_not_called()
    assert not root.exists()


def test_partial_cache_is_not_refilled_or_migrated(tmp_path, monkeypatch):
    root = tmp_path / "research"
    store = OHLCVStore(root)
    frame = pd.DataFrame({"date": pd.to_datetime(["2025-01-02"]),
                          "open": [10.0], "high": [11.0], "low": [9.0],
                          "close": [10.0], "volume": [100.0], "amount": [1000.0]})
    store.save("510300", frame)
    before = (root / "market_data.db").read_bytes()
    monkeypatch.setattr(OHLCVStore, "_migrate_legacy_csvs",
                        Mock(side_effect=AssertionError("migration forbidden")))
    monkeypatch.setattr(AkShareMarketDataProvider, "_fetch_tencent",
                        Mock(side_effect=AssertionError("network forbidden")))
    provider = _training_provider(None, root)
    assert len(provider.history("510300", date(2025, 1, 2), date(2025, 1, 2))) == 1
    assert provider.cache_revision() == store.revision()
    with pytest.raises(UpstreamUnavailableError, match="cannot fetch or write"):
        provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))
    with pytest.raises(ValueError, match="read-only"):
        provider._storage.save("510300", frame)
    assert (root / "market_data.db").read_bytes() == before


def test_training_rejects_default_live_cache(tmp_path, monkeypatch):
    root = tmp_path / "live"
    monkeypatch.setenv("QUANT_DATA_DIR", str(root))
    with pytest.raises(RLInvalidSplit, match="研究"):
        _training_provider(None, root)
    assert not root.exists()
