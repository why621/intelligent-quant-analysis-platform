from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_cloud_candidate_is_isolated_readonly_and_bounded():
    value = yaml.safe_load((ROOT / "deploy/mvp/compose.yml").read_text())
    backend = value["services"]["backend"]
    gateway = value["services"]["gateway"]
    assert value["name"] == "quant-mvp-cr026"
    assert "ports" not in backend
    assert "./publication:/app/publication:ro" in backend["volumes"]
    assert backend["environment"]["GUNICORN_WORKERS"] == 1
    assert backend["environment"]["ALLOWED_ORIGINS"] == "https://why621.github.io,https://43.161.223.91"
    assert "X-Research-Version" in backend["environment"]["CORS_ALLOW_HEADERS"]
    assert gateway["ports"] == ["127.0.0.1:8081:8080", "443:8443"]
    assert "market-data" not in str(value) and "backtest-data" not in str(value)


def test_tls_never_uses_internal_or_untrusted_certificate():
    tls = (ROOT / "deploy/mvp/nginx-tls.conf").read_text()
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in tls
    assert "/etc/letsencrypt/live/43.161.223.91/fullchain.pem" in tls
    assert "ssl_verify_client off" not in tls
    limits = (ROOT / "deploy/mvp/nginx-api.conf").read_text()
    assert "client_max_body_size 64k" in limits
    assert "limit_req zone=globaljobs" in limits
    assert "limit_conn allclients 24" in limits
