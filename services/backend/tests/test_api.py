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
        client.get("/api/assets"),
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
