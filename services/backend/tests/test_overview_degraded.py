from unittest.mock import patch

from app import create_app


def test_empty_overview_returns_503_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKTEST_DB_PATH", str(tmp_path / "backtests.db"))
    app = create_app()
    provider = app.extensions["market_data_service"]._provider
    with patch.object(provider, "_fetch_overview_bounded") as fetch:
        response = app.test_client().get("/api/market/overview")
    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    fetch.assert_not_called()


def test_status_exposes_components_independently(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKTEST_DB_PATH", str(tmp_path / "backtests.db"))
    app = create_app()
    provider = app.extensions["market_data_service"]._provider
    components = {
        "history": {"status": "ready", "message": "complete"},
        "overview": {"status": "failed", "message": "no snapshot"},
    }
    provider._status_storage.save("stale", None, "partial", components=components)
    response = app.test_client().get("/api/data/status")
    assert response.status_code == 200
    assert response.json["components"] == components
