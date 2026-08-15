from app import create_app


def make_client():
    application = create_app({"TESTING": True})
    return application.test_client()


def test_health_matches_contract() -> None:
    response = make_client().get("/api/health")

    assert response.status_code == 200
    assert response.json == {
        "status": "ok",
        "service": "intelligent-quant-backend",
        "version": "0.1.0",
    }


def test_all_contract_paths_are_registered_as_explicit_placeholders() -> None:
    client = make_client()
    calls = [
        client.get("/api/assets/510300/history?startDate=2025-01-01&endDate=2025-12-31"),
        client.get("/api/market/overview"),
        client.post(
            "/api/analytics/correlation",
            json={
                "symbols": ["510300", "510500"],
                "startDate": "2025-01-01",
                "endDate": "2025-12-31",
            },
        ),
        client.get("/api/strategies"),
        client.get("/api/strategies/ranking?period=30d"),
        client.post("/api/backtests", json={"strategyId": "ma_cross"}),
        client.get("/api/backtests/8f316d85-e86b-45c5-8ff6-c8ee2457e71b"),
        client.post(
            "/api/allocation/suggestion",
            json={"symbols": ["510300"], "strategyId": "ma_cross"},
        ),
    ]

    assert all(response.status_code == 501 for response in calls)
    assert all(response.json["error"]["code"] == "NOT_IMPLEMENTED" for response in calls)


def test_data_status_matches_contract() -> None:
    response = make_client().get("/api/data/status")

    assert response.status_code == 200
    body = response.json
    assert body["status"] in {"ready", "updating", "stale", "failed"}
    assert body["timezone"] == "Asia/Shanghai"
    assert body["source"] == "AkShare"
    assert isinstance(body["assetCount"], int) and body["assetCount"] >= 0
    assert body["latestTradeDate"] is None or isinstance(body["latestTradeDate"], str)
    assert body["updatedAt"] is None or isinstance(body["updatedAt"], str)
    assert "message" in body


def test_assets_matches_contract() -> None:
    response = make_client().get("/api/assets")

    assert response.status_code == 200
    body = response.json
    assert set(body) == {"items", "total"}
    assert isinstance(body["total"], int) and body["total"] == len(body["items"])
    assert body["total"] > 0
    for item in body["items"]:
        assert set(item) == {"symbol", "name", "assetType", "exchange", "active"}
        assert isinstance(item["symbol"], str) and len(item["symbol"]) == 6
        assert item["assetType"] in {"stock", "etf"}
        assert item["exchange"] in {"SSE", "SZSE", "BSE"}
        assert isinstance(item["active"], bool)


def test_assets_filters_and_limits() -> None:
    client = make_client()

    etf_only = client.get("/api/assets?assetType=etf")
    assert etf_only.status_code == 200
    assert all(item["assetType"] == "etf" for item in etf_only.json["items"])

    limited = client.get("/api/assets?limit=5")
    assert limited.status_code == 200
    assert len(limited.json["items"]) == 5
    assert limited.json["total"] == 5

    searched = client.get("/api/assets?query=510300")
    assert searched.status_code == 200
    assert any(item["symbol"] == "510300" for item in searched.json["items"])


def test_assets_rejects_invalid_params() -> None:
    client = make_client()

    bad_type = client.get("/api/assets?assetType=fund")
    assert bad_type.status_code == 400
    assert bad_type.json["error"]["code"] == "VALIDATION_ERROR"
    assert bad_type.json["error"]["details"] == {"field": "assetType"}

    bad_limit = client.get("/api/assets?limit=0")
    assert bad_limit.status_code == 400
    assert bad_limit.json["error"]["code"] == "VALIDATION_ERROR"

    long_query = client.get("/api/assets?query=" + "长" * 31)
    assert long_query.status_code == 400
    assert long_query.json["error"]["code"] == "VALIDATION_ERROR"


def test_post_interface_rejects_non_json_body() -> None:
    response = make_client().post("/api/backtests", data="not-json")

    assert response.status_code == 400
    assert response.json == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "请求体必须是 JSON 对象",
            "details": {"field": "body"},
        }
    }
