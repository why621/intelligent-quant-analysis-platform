"""Synthetic, isolated HTTP/cache acceptance; not a claim of live upstream success."""

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import pandas as pd
import pytest
from quant_platform.data import market_fetch

from app import create_app


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANT_DATA_DIR", str(tmp_path))
    application = create_app({"TESTING": True, "ALLOWED_ORIGINS": "https://why621.github.io"})
    provider = application.extensions["market_data_service"]._provider
    day = date.today()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    provider._storage.save(
        "510300",
        pd.DataFrame(
            {
                "date": [pd.Timestamp(day)],
                "open": [1],
                "high": [2],
                "low": [1],
                "close": [2],
                "volume": [100],
                "amount": [None],
            }
        ),
    )
    provider._status_storage.save(
        "ready",
        day,
        "synthetic fixture",
        components={
            "history": {"status": "ready"},
            "overview": {"status": "ready"},
        },
    )
    timestamp = pd.Timestamp(day).tz_localize("Asia/Shanghai").timestamp()
    provider._overview_storage.save(
        market_fetch.summarise([{"f3": 1, "f6": 10, "f124": timestamp}], day)
    )
    path = Path(__file__).resolve().parents[3] / "tools" / "smoke_regression.py"
    spec = importlib.util.spec_from_file_location("regression_smoke", path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    client = application.test_client()

    def fetch(url, origin=None):
        parsed = urlsplit(url)
        response = client.get(
            parsed.path + ("?" + parsed.query if parsed.query else ""),
            headers={"Origin": origin} if origin else {},
        )
        if origin:
            assert response.headers["Access-Control-Allow-Origin"] == origin
        return response.status_code, response.content_type, response.get_data(as_text=True)

    monkeypatch.setattr(smoke, "fetch", fetch)
    return smoke, provider, client


def test_strict_acceptance_reads_validated_cache_and_pages_cors(stack):
    smoke, provider, client = stack
    with patch.object(provider, "_fetch_tencent", side_effect=AssertionError("unexpected network")):
        smoke.verify_live_data("http://local.test", "https://why621.github.io")
    response = client.get("/api/market/overview")
    assert response.json["limitUp"] is None
    assert response.json["unavailableMetrics"] == ["limitUp", "limitDown"]


def test_healthy_but_stale_fails_strict_acceptance(stack):
    smoke, provider, client = stack
    assert client.get("/api/health").status_code == 200
    provider._status_storage.save("stale", date.today(), "fixture outage")
    with pytest.raises(RuntimeError, match="not ready"):
        smoke.verify_live_data("http://local.test")


def test_html_success_is_not_json_acceptance(stack, monkeypatch):
    smoke, _, _ = stack
    monkeypatch.setattr(smoke, "fetch", lambda *args: (200, "text/html", "<html></html>"))
    with pytest.raises(RuntimeError, match="JSON"):
        smoke.verify_live_data("http://local.test")
