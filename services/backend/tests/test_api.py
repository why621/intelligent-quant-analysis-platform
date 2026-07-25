from app import create_app


def make_client():
    application = create_app({"TESTING": True})
    return application.test_client()


def test_health_interface() -> None:
    response = make_client().get("/api/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["version"] == "0.1.0"
    assert response.json["time"]


def test_defined_interfaces_return_explicit_pending_status() -> None:
    client = make_client()
    calls = [
        client.get("/api/market/overview"),
        client.post("/api/analytics/correlation", json={"assets": ["A", "B"]}),
        client.post("/api/backtests", json={"strategy": "ma_crossover"}),
        client.get("/api/strategies/ranking"),
        client.post("/api/allocation/suggestion", json={"assets": ["A", "B"]}),
    ]

    assert all(response.status_code == 501 for response in calls)
    assert all(response.json["code"] == "NOT_IMPLEMENTED" for response in calls)
    assert all(response.json["traceId"].startswith("req_") for response in calls)


def test_post_interface_rejects_non_json_body() -> None:
    response = make_client().post("/api/backtests", data="not-json")

    assert response.status_code == 400
    assert response.json["code"] == "INVALID_ARGUMENT"
