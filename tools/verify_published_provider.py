"""Offline five-module gate against a validated immutable candidate."""
from app import create_app


def verify(provider):
    app = create_app({"TESTING": True}, market_data_provider=provider)
    client = app.test_client()
    context = provider.publication_context

    def checked(response, status=200):
        value = response.get_json()
        if response.status_code != status:
            raise ValueError(f"five-module gate: {response.status_code}: {value}")
        if "dataContext" in value and value["dataContext"] != context:
            raise ValueError("mixed publication context")
        return value

    coverage = checked(client.get("/api/data/coverage"))
    if len(coverage["items"]) != 327:
        raise ValueError("incomplete coverage")
    overview = checked(client.get("/api/market/overview"))
    symbols = ["600438", "600958", "601059", "601995", "688012", "688072", "688521", "001280", "002049", "300442"]
    dates = {"startDate": provider.start.isoformat(), "endDate": provider.end.isoformat()}
    correlation = checked(client.post("/api/analytics/correlation", json={"symbols": symbols, **dates}))
    if len(correlation["matrix"]) != 10:
        raise ValueError("incomplete correlation")
    ranking = checked(client.get("/api/strategies/ranking?period=30d"))
    allocation = checked(client.post("/api/allocation/suggestion", json={"symbols": ["510300"], "strategyId": "ma_cross"}))
    if abs(sum(p["weightPct"] for p in allocation["positions"]) + allocation["cashPct"] - 100) > 0.01:
        raise ValueError("allocation weights do not conserve capital")
    jobs = []
    strategies = checked(client.get("/api/strategies"))["items"]
    for strategy in strategies:
        parameters = {key: rule["default"] for key, rule in strategy["parameterSchema"]["properties"].items()}
        job = checked(client.post("/api/backtests", json={"symbols": ["600438", "001280"], **dates, "strategyId": strategy["id"], "parameters": parameters, "benchmark": "index:CSI:000300"}), 202)
        app.extensions["backtest_service"].execute_job(job["jobId"])
        result = checked(client.get("/api/backtests/" + job["jobId"]))
        if result["status"] != "succeeded" or result["result"]["assumptions"]["benchmarkReturnBasis"] != "price_index":
            raise ValueError("index backtest gate failed")
        jobs.append({"jobId": job["jobId"], "strategyId": strategy["id"], "status": result["status"]})
    return {"dataContext": context, "overview": overview, "correlationObservations": correlation["observationCount"], "ranking": ranking, "allocation": allocation, "jobs": jobs}
