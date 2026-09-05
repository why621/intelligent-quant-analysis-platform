from pathlib import Path

from quant_platform.data.akshare_provider import AkShareMarketDataProvider


def test_provider_uses_configured_data_directory(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "market-data"
    monkeypatch.setenv("QUANT_DATA_DIR", str(configured))

    provider = AkShareMarketDataProvider()

    assert provider._storage.data_dir == configured.resolve()
    assert provider._status_storage._data_dir == configured.resolve()
