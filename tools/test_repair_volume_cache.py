import pandas as pd
import pytest
from quant_platform.data.akshare_provider import AkShareMarketDataProvider

from tools.repair_volume_cache import connect, fingerprint, repair


def bars(volume):
    return pd.DataFrame({"date": pd.to_datetime(["2026-09-04", "2026-09-07"]),
                         "open": 10., "high": 11., "low": 9., "close": 10.,
                         "volume": volume, "amount": 1000.})


def seeded(tmp_path):
    path = tmp_path / "data"
    provider = AkShareMarketDataProvider(path)
    for symbol in ("000001", "000333", "510300"):
        provider._storage.save(symbol, bars(1.))
    return path, provider


def test_apply_preserves_other_assets_and_backup(tmp_path):
    path, provider = seeded(tmp_path)
    result = repair(path, tmp_path / "backup", apply=True, fetcher=lambda *args: bars(100.))
    assert result["targets"] == 2
    assert provider._load_history_cache("000001")["volume"].tolist() == [100., 100.]
    assert provider._storage.load("510300")["volume"].tolist() == [1., 1.]
    with connect(tmp_path / "backup/market_data.original.db") as saved:
        assert saved.execute("SELECT volume FROM ohlcv WHERE symbol='000001'").fetchone()[0] == 1
    again = repair(path, tmp_path / "again", apply=True,
                   fetcher=lambda *args: pytest.fail("already verified"))
    assert again["status"] == "already_verified"


def test_failed_fetch_never_applies_partial_batch(tmp_path):
    path, provider = seeded(tmp_path)
    before = provider.cache_revision()
    def fetch(symbol, *args):
        if symbol == "000333":
            raise RuntimeError("network failed")
        return bars(100.)
    with pytest.raises(RuntimeError):
        repair(path, tmp_path / "backup", apply=True, fetcher=fetch)
    assert provider.cache_revision() == before
    assert provider._storage.load("000001")["volume"].tolist() == [1., 1.]


def test_source_change_refuses_apply(tmp_path):
    path, provider = seeded(tmp_path)
    def fetch(*args):
        provider._storage.save("510300", bars(7.))
        return bars(100.)
    with pytest.raises(ValueError, match="source changed"):
        repair(path, tmp_path / "backup", apply=True, fetcher=fetch)
    assert provider._storage.load("000001")["volume"].tolist() == [1., 1.]
    assert provider._storage.load("510300")["volume"].tolist() == [7., 7.]


def test_incomplete_dates_rejected(tmp_path):
    path, _ = seeded(tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        repair(path, tmp_path / "backup", apply=True, fetcher=lambda *a: bars(100.).tail(1))


def test_prepare_is_read_only_and_backup_must_be_new(tmp_path):
    path, _ = seeded(tmp_path)
    with connect(path / "market_data.db") as db:
        before = fingerprint(db)
    repair(path, tmp_path / "backup", fetcher=lambda *a: bars(100.))
    with connect(path / "market_data.db") as db:
        assert fingerprint(db) == before
    with pytest.raises(FileExistsError):
        repair(path, tmp_path / "backup")
