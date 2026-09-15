"""Offline five-module gate against a validated immutable candidate."""

from app import create_app


def verify(provider):
    if not provider.availability["complete"]:
        return verify_partial(provider)
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
    symbols = [
        "600438",
        "600958",
        "601059",
        "601995",
        "688012",
        "688072",
        "688521",
        "001280",
        "002049",
        "300442",
    ]
    dates = {
        "startDate": provider.start.isoformat(),
        "endDate": provider.end.isoformat(),
    }
    correlation = checked(
        client.post("/api/analytics/correlation", json={"symbols": symbols, **dates})
    )
    if len(correlation["matrix"]) != 10:
        raise ValueError("incomplete correlation")
    ranking = checked(client.get("/api/strategies/ranking?period=30d"))
    allocation = checked(
        client.post(
            "/api/allocation/suggestion",
            json={"symbols": ["510300"], "strategyId": "ma_cross"},
        )
    )
    if (
        abs(
            sum(p["weightPct"] for p in allocation["positions"])
            + allocation["cashPct"]
            - 100
        )
        > 0.01
    ):
        raise ValueError("allocation weights do not conserve capital")
    jobs = []
    strategies = checked(client.get("/api/strategies"))["items"]
    for strategy in strategies:
        parameters = {
            key: rule["default"]
            for key, rule in strategy["parameterSchema"]["properties"].items()
        }
        job = checked(
            client.post(
                "/api/backtests",
                json={
                    "symbols": ["600438", "001280"],
                    **dates,
                    "strategyId": strategy["id"],
                    "parameters": parameters,
                    "benchmark": "index:CSI:000300",
                },
            ),
            202,
        )
        app.extensions["backtest_service"].execute_job(job["jobId"])
        result = checked(client.get("/api/backtests/" + job["jobId"]))
        if (
            result["status"] != "succeeded"
            or result["result"]["assumptions"]["benchmarkReturnBasis"] != "price_index"
        ):
            raise ValueError("index backtest gate failed")
        jobs.append(
            {
                "jobId": job["jobId"],
                "strategyId": strategy["id"],
                "status": result["status"],
            }
        )
    return {
        "dataContext": context,
        "overview": overview,
        "correlationObservations": correlation["observationCount"],
        "ranking": ranking,
        "allocation": allocation,
        "jobs": jobs,
    }


def verify_partial(provider):
    """A partial gate verifies declared capabilities and rejects unknown-gap reads."""
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    app = create_app({"TESTING": True}, market_data_provider=provider)
    client = app.test_client()
    context = provider.publication_context
    outcomes = {}
    for path in ("/api/data/status", "/api/data/coverage", "/api/market/overview"):
        r = client.get(path)
        if r.status_code != 200 or r.json.get("dataContext") != context:
            raise ValueError("partial release status/context gate failed")
    available = []
    for symbol, state in provider.availability["assets"].items():
        if state["state"] == "ready":
            provider.history(symbol, provider.start, provider.end)
            available.append(symbol)
        elif state["missingSessions"]:
            try:
                provider.history(symbol, provider.start, provider.end)
            except UpstreamUnavailableError:
                continue
            raise ValueError("unknown-gap history unexpectedly accepted")
    dates = {
        "startDate": provider.start.isoformat(),
        "endDate": provider.end.isoformat(),
    }
    if len(available) >= 2:
        r = client.post(
            "/api/analytics/correlation", json={"symbols": available[:2], **dates}
        )
        if r.status_code != 200:
            raise ValueError("available-asset correlation gate failed")
        outcomes["correlation"] = "passed"
        strategies = client.get("/api/strategies").json["items"]
        for strategy in strategies:
            sid = strategy["id"]
            parameters = {
                k: v["default"]
                for k, v in strategy["parameterSchema"]["properties"].items()
            }
            r = client.post(
                "/api/backtests",
                json={
                    "symbols": available[:2],
                    **dates,
                    "strategyId": sid,
                    "parameters": parameters,
                },
            )
            if r.status_code != 202:
                raise ValueError(
                    f"available-asset backtest submission failed: {r.json}"
                )
            app.extensions["backtest_service"].execute_job(r.json["jobId"])
            if (
                client.get("/api/backtests/" + r.json["jobId"]).json["status"]
                != "succeeded"
            ):
                raise ValueError("available-asset backtest failed")
        outcomes["backtest"] = "passed"
    else:
        outcomes.update(
            correlation="unavailable: fewer than two complete assets",
            backtest="not exercised: fewer than two complete assets",
        )
    if "510300" in available:
        if client.get("/api/strategies/ranking?period=30d").status_code != 200:
            raise ValueError("ranking dependency gate failed")
        outcomes["ranking"] = "passed: 510300"
    else:
        outcomes["ranking"] = "unavailable: 510300 incomplete"
    tradable = [
        s for s in available if not provider.availability["assets"][s]["suspended"]
    ]
    if tradable:
        r = client.post(
            "/api/allocation/suggestion",
            json={"symbols": tradable[:1], "strategyId": "ma_cross"},
        )
        if r.status_code != 200:
            raise ValueError("allocation dependency gate failed")
        if (
            abs(
                r.json["cashPct"]
                + sum(p["weightPct"] for p in r.json["positions"])
                - 100
            )
            > 0.01
        ):
            raise ValueError("allocation weights invalid")
        outcomes["allocation"] = "passed"
    else:
        outcomes["allocation"] = "unavailable: no complete tradable assets"
    return {
        "dataContext": context,
        "partial": True,
        "modules": outcomes,
        "availability": {
            k: v for k, v in provider.availability.items() if k != "assets"
        },
    }
