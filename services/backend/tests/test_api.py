import re

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


def make_client_with_fake(method_name: str, fake_value):
    """把 provider 的 method_name 替换为返回 fake_value 的函数，避免真实网络请求。"""
    application = create_app({"TESTING": True})
    service = application.extensions["market_data_service"]
    setattr(service._provider, method_name, lambda *args, **kwargs: fake_value)
    return application.test_client()


FAKE_HISTORY = {
    "date": ["2025-01-03", "2025-01-06", "2025-01-07"],
    "open": [3.95, 3.98, 4.01],
    "high": [4.02, 4.05, 4.06],
    "low": [3.94, 3.96, 3.99],
    "close": [4.01, 4.02, 4.05],
    "volume": [823456700.0, 800123400.0, 912345600.0],
    "amount": [3302511234.56, 3250012345.67, 3600123456.78],
}


def test_asset_history_matches_contract() -> None:
    from pandas import DataFrame

    client = make_client_with_fake("history", DataFrame(FAKE_HISTORY))
    response = client.get(
        "/api/assets/510300/history?startDate=2025-01-01&endDate=2025-12-31"
    )

    assert response.status_code == 200
    body = response.json
    assert body["symbol"] == "510300"
    assert body["adjust"] == "qfq"
    assert body["currency"] == "CNY"
    assert len(body["items"]) == 3
    assert body["items"][0]["date"] == "2025-01-03"
    assert body["items"][0]["amount"] == 3302511234.56
    dates = [item["date"] for item in body["items"]]
    assert dates == sorted(dates)


def test_asset_history_empty_frame_is_empty_items() -> None:
    from pandas import DataFrame

    empty = DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
    client = make_client_with_fake("history", empty)
    response = client.get(
        "/api/assets/510300/history?startDate=2025-01-01&endDate=2025-12-31"
    )

    # 新 provider 语义：空 DataFrame = 区间真无数据，返回 200 空 items（不是错误）
    assert response.status_code == 200
    assert response.json["items"] == []


def test_asset_history_upstream_error() -> None:
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    def failing(*args, **kwargs):
        raise UpstreamUnavailableError("Tencent history failed")

    application = create_app({"TESTING": True})
    service = application.extensions["market_data_service"]
    service._provider.history = failing
    client = application.test_client()
    response = client.get(
        "/api/assets/510300/history?startDate=2025-01-01&endDate=2025-12-31"
    )

    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_asset_history_asset_not_in_pool() -> None:
    response = make_client().get(
        "/api/assets/999999/history?startDate=2025-01-01&endDate=2025-12-31"
    )

    assert response.status_code == 404
    assert response.json["error"]["code"] == "ASSET_NOT_FOUND"


def test_asset_history_rejects_invalid_params() -> None:
    client = make_client()

    bad_symbol = client.get("/api/assets/abc123/history?startDate=2025-01-01&endDate=2025-12-31")
    assert bad_symbol.status_code == 400
    assert bad_symbol.json["error"]["code"] == "VALIDATION_ERROR"

    missing_date = client.get("/api/assets/510300/history?startDate=2025-01-01")
    assert missing_date.status_code == 400
    assert missing_date.json["error"]["code"] == "VALIDATION_ERROR"

    bad_date = client.get("/api/assets/510300/history?startDate=2025/01/01&endDate=2025-12-31")
    assert bad_date.status_code == 400
    assert bad_date.json["error"]["code"] == "VALIDATION_ERROR"

    reversed_range = client.get(
        "/api/assets/510300/history?startDate=2025-12-31&endDate=2025-01-01"
    )
    assert reversed_range.status_code == 400

    bad_adjust = client.get(
        "/api/assets/510300/history?startDate=2025-01-01&endDate=2025-12-31&adjust=xxx"
    )
    assert bad_adjust.status_code == 400
    assert bad_adjust.json["error"]["details"] == {"field": "adjust"}


FAKE_OVERVIEW = {
    "tradeDate": "2026-08-14",
    "advancing": 3200,
    "declining": 1800,
    "unchanged": 120,
    "limitUp": 45,
    "limitDown": 8,
    "turnoverCny": 850000000000.0,
    "northboundNetCny": 1234567890.0,
    "indices": [
        {"symbol": "000001", "name": "上证指数", "close": 3456.78, "changePct": 0.55},
        {"symbol": "000300", "name": "沪深300", "close": 4123.45, "changePct": 0.82},
    ],
}


def test_market_overview_matches_contract() -> None:
    client = make_client_with_fake("market_overview", FAKE_OVERVIEW)
    response = client.get("/api/market/overview")

    assert response.status_code == 200
    body = response.json
    assert set(body) == {
        "tradeDate", "advancing", "declining", "unchanged",
        "limitUp", "limitDown", "turnoverCny", "northboundNetCny", "indices",
    }
    assert body["tradeDate"] == "2026-08-14"
    assert body["advancing"] == 3200
    assert body["turnoverCny"] == 850000000000.0
    assert body["indices"][0] == {
        "symbol": "000001", "name": "上证指数", "close": 3456.78, "changePct": 0.55,
    }


def test_market_overview_upstream_error() -> None:
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    def failing(*args, **kwargs):
        raise UpstreamUnavailableError("market overview upstream failed")

    application = create_app({"TESTING": True})
    service = application.extensions["market_data_service"]
    service._provider.market_overview = failing
    response = application.test_client().get("/api/market/overview")

    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_market_overview_ignores_trade_date_param() -> None:
    """tradeDate 查询参数被忽略：即使格式非法也正常返回最新快照。"""
    client = make_client_with_fake("market_overview", FAKE_OVERVIEW)
    response = client.get("/api/market/overview?tradeDate=not-a-date")

    assert response.status_code == 200
    assert response.json["tradeDate"] == "2026-08-14"


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


# ---------------------------------------------------------------------------
# GET /strategies
# ---------------------------------------------------------------------------


def test_strategies_matches_contract() -> None:
    response = make_client().get("/api/strategies")

    assert response.status_code == 200
    body = response.json
    assert set(body) == {"items"}
    items = body["items"]
    assert len(items) >= 1
    for item in items:
        assert set(item) == {
            "id", "name", "category", "status", "description", "parameterSchema",
        }
        assert item["category"] in {"traditional", "ai"}
        assert item["status"] in {"available", "experimental", "planned"}
        assert isinstance(item["parameterSchema"], dict)


def test_strategies_catalog_contains_known_strategies() -> None:
    response = make_client().get("/api/strategies")

    by_id = {item["id"]: item for item in response.json["items"]}
    assert set(by_id) == {"ma_cross", "momentum_reversal"}
    ma_cross = by_id["ma_cross"]
    assert ma_cross["status"] == "available"
    assert set(ma_cross["parameterSchema"]["required"]) == {"shortWindow", "longWindow"}


# ---------------------------------------------------------------------------
# POST /analytics/correlation
# ---------------------------------------------------------------------------


def make_client_with_correlation(fake_result):
    """把 correlation 服务的 analyzer.calculate 替换为返回 fake_result 的函数。"""
    application = create_app({"TESTING": True})
    service = application.extensions["correlation_service"]
    service._analyzer.calculate = lambda request: fake_result
    return application.test_client()


CORRELATION_BODY = {
    "symbols": ["510300", "510500"],
    "startDate": "2025-01-01",
    "endDate": "2025-12-31",
}


def test_correlation_matches_contract() -> None:
    from quant_platform.models import CorrelationResult

    fake = CorrelationResult(
        symbols=("510300", "510500"),
        observation_count=245,
        matrix=((1.0, 0.87), (0.87, 1.0)),
    )
    response = make_client_with_correlation(fake).post(
        "/api/analytics/correlation", json=CORRELATION_BODY
    )

    assert response.status_code == 200
    body = response.json
    assert set(body) == {"symbols", "observationCount", "matrix"}
    assert body["symbols"] == ["510300", "510500"]
    assert body["observationCount"] == 245
    assert body["matrix"] == [[1.0, 0.87], [0.87, 1.0]]


def test_correlation_nan_converted_to_null() -> None:
    from quant_platform.models import CorrelationResult

    fake = CorrelationResult(
        symbols=("510300", "510500"),
        observation_count=120,
        matrix=((1.0, float("nan")), (float("nan"), float("nan"))),
    )
    response = make_client_with_correlation(fake).post(
        "/api/analytics/correlation", json=CORRELATION_BODY
    )

    assert response.status_code == 200
    assert response.json["matrix"] == [[1.0, None], [None, None]]


def test_correlation_insufficient_data() -> None:
    from quant_platform.models import CorrelationResult

    for count in (0, 1):
        fake = CorrelationResult(
            symbols=("510300", "510500"),
            observation_count=count,
            matrix=((0.0, 0.0), (0.0, 0.0)),
        )
        response = make_client_with_correlation(fake).post(
            "/api/analytics/correlation", json=CORRELATION_BODY
        )

        assert response.status_code == 422
        assert response.json["error"]["code"] == "INSUFFICIENT_DATA"


def test_correlation_upstream_error() -> None:
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    def failing(*args, **kwargs):
        raise UpstreamUnavailableError("Tencent history failed")

    application = create_app({"TESTING": True})
    service = application.extensions["market_data_service"]
    # correlation 复用同一个 provider 实例，替换 history 即模拟上游失败
    service._provider.history = failing
    response = application.test_client().post(
        "/api/analytics/correlation", json=CORRELATION_BODY
    )

    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_correlation_rejects_invalid_body() -> None:
    client = make_client()

    bad_symbols = [
        dict(CORRELATION_BODY, symbols=["510300"]),           # 少于 2 个
        dict(CORRELATION_BODY, symbols=list(range(11))),      # 超过 10 个
        dict(CORRELATION_BODY, symbols=["510300", "510300"]),  # 重复
        dict(CORRELATION_BODY, symbols=["510300", "abc123"]),  # 非六位数字
        dict(CORRELATION_BODY, symbols=["510300", 510500]),   # 非字符串
        dict(CORRELATION_BODY, extra="field"),                # 未知字段
    ]
    for body in bad_symbols:
        response = client.post("/api/analytics/correlation", json=body)
        assert response.status_code == 400
        assert response.json["error"]["code"] == "VALIDATION_ERROR"

    missing_date = dict(CORRELATION_BODY)
    del missing_date["startDate"]
    response = client.post("/api/analytics/correlation", json=missing_date)
    assert response.status_code == 400
    assert response.json["error"]["details"] == {"field": "startDate"}

    bad_date = dict(CORRELATION_BODY, startDate="2025/01/01")
    response = client.post("/api/analytics/correlation", json=bad_date)
    assert response.status_code == 400

    reversed_range = dict(CORRELATION_BODY, startDate="2025-12-31", endDate="2025-01-01")
    response = client.post("/api/analytics/correlation", json=reversed_range)
    assert response.status_code == 400

    for field, value in (("adjust", "xxx"), ("returnType", "linear")):
        response = client.post(
            "/api/analytics/correlation",
            json=dict(CORRELATION_BODY, **{field: value}),
        )
        assert response.status_code == 400
        assert response.json["error"]["details"] == {"field": field}
def make_client_with_backtest(engine_run):
    """fake 资产池并替换回测引擎的 run，避免真实计算与网络请求。

    backtest_service 与 market_data_service 共享同一个 provider 实例，
    替换 list_assets 即同时影响两者的资产池校验。
    """
    from quant_platform.models import Asset

    client = make_client_with_fake(
        "list_assets",
        [
            Asset(symbol="510300", name="沪深300ETF", asset_type="etf", exchange="SSE"),
            Asset(symbol="510500", name="中证500ETF", asset_type="etf", exchange="SSE"),
        ],
    )
    backtest_service = client.application.extensions["backtest_service"]
    backtest_service._engine.run = engine_run
    return client, backtest_service


BACKTEST_BODY = {
    "symbols": ["510300"],
    "strategyId": "ma_cross",
    "parameters": {"shortWindow": 5, "longWindow": 20},
    "startDate": "2024-01-01",
    "endDate": "2025-12-31",
}


def fake_backtest_result():
    from datetime import date as date_cls

    from pandas import DataFrame
    from quant_platform.models import BacktestMetrics, BacktestResult, Trade

    return BacktestResult(
        metrics=BacktestMetrics(
            total_return_pct=8.5,
            annualized_return_pct=8.5,
            max_drawdown_pct=5.2,
            sharpe=1.1,
            alpha_pct=None,
            beta=None,
        ),
        equity_curve=DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "equity": [100000.0, 100500.0],
                "benchmarkEquity": [1.0, 1.005],
            }
        ),
        trades=(
            Trade(
                trade_date=date_cls(2024, 1, 2),
                symbol="510300",
                side="buy",
                price=3.95,
                quantity=25250.0,
                amount_cny=99737.5,
                fee_cny=29.92,
            ),
        ),
        assumptions={
            "signalAt": "close",
            "executeAt": "next_open",
            "calendar": "CN",
            "currency": "CNY",
        },
    )


def test_backtest_create_matches_contract() -> None:
    client, _ = make_client_with_backtest(lambda request: None)
    response = client.post("/api/backtests", json=BACKTEST_BODY)

    assert response.status_code == 202
    body = response.json
    assert set(body) == {
        "jobId", "status", "createdAt", "updatedAt", "progressPct", "result", "error",
    }
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        body["jobId"],
    )
    assert body["status"] == "queued"
    assert body["updatedAt"] is None
    assert body["progressPct"] == 0
    assert body["result"] is None
    assert body["error"] is None
    assert "T" in body["createdAt"]  # ISO 8601 datetime


def test_backtest_executes_and_returns_result() -> None:
    client, backtest_service = make_client_with_backtest(
        lambda request: fake_backtest_result()
    )
    job_id = client.post("/api/backtests", json=BACKTEST_BODY).json["jobId"]

    backtest_service.execute_job(job_id)
    response = client.get(f"/api/backtests/{job_id}")

    assert response.status_code == 200
    body = response.json
    assert body["status"] == "succeeded"
    assert body["progressPct"] == 100
    assert body["error"] is None
    result = body["result"]
    assert set(result) == {"metrics", "equityCurve", "trades", "assumptions"}
    assert result["metrics"] == {
        "totalReturnPct": 8.5,
        "annualizedReturnPct": 8.5,
        "maxDrawdownPct": 5.2,
        "sharpe": 1.1,
        "alphaPct": None,
        "beta": None,
    }
    assert result["equityCurve"] == [
        {"date": "2024-01-02", "equity": 100000.0, "benchmarkEquity": 1.0},
        {"date": "2024-01-03", "equity": 100500.0, "benchmarkEquity": 1.005},
    ]
    assert result["trades"] == [
        {
            "date": "2024-01-02",
            "symbol": "510300",
            "side": "buy",
            "price": 3.95,
            "quantity": 25250.0,
            "amountCny": 99737.5,
            "feeCny": 29.92,
        }
    ]
    assert result["assumptions"] == {
        "signalAt": "close",
        "executeAt": "next_open",
        "calendar": "CN",
        "currency": "CNY",
    }


def test_backtest_failed_error() -> None:
    def failing(request):
        raise RuntimeError("boom")

    client, backtest_service = make_client_with_backtest(failing)
    job_id = client.post("/api/backtests", json=BACKTEST_BODY).json["jobId"]

    backtest_service.execute_job(job_id)
    body = client.get(f"/api/backtests/{job_id}").json

    assert body["status"] == "failed"
    assert body["result"] is None
    assert body["error"]["error"]["code"] == "INTERNAL_ERROR"


def test_backtest_upstream_error() -> None:
    from quant_platform.data.akshare_provider import UpstreamUnavailableError

    def failing(request):
        raise UpstreamUnavailableError("Tencent history failed")

    client, backtest_service = make_client_with_backtest(failing)
    job_id = client.post("/api/backtests", json=BACKTEST_BODY).json["jobId"]

    backtest_service.execute_job(job_id)
    body = client.get(f"/api/backtests/{job_id}").json

    assert body["status"] == "failed"
    assert body["error"]["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_backtest_job_not_found() -> None:
    response = make_client().get(
        "/api/backtests/8f316d85-e86b-45c5-8ff6-c8ee2457e71b"
    )

    assert response.status_code == 404
    assert response.json["error"]["code"] == "JOB_NOT_FOUND"


def test_backtest_rejects_invalid_job_id() -> None:
    response = make_client().get("/api/backtests/not-a-uuid")

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
    assert response.json["error"]["details"] == {"field": "jobId"}


def test_backtest_strategy_not_available() -> None:
    client, _ = make_client_with_backtest(lambda request: None)
    response = client.post(
        "/api/backtests", json=dict(BACKTEST_BODY, strategyId="unknown")
    )

    assert response.status_code == 422
    assert response.json["error"]["code"] == "STRATEGY_NOT_AVAILABLE"


def test_backtest_invalid_parameters() -> None:
    client, _ = make_client_with_backtest(lambda request: None)
    response = client.post(
        "/api/backtests",
        json=dict(BACKTEST_BODY, parameters={"shortWindow": 20, "longWindow": 5}),
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
    # 策略级语义校验的具体原因必须透出（ServiceError 自定义 message）
    assert "shortWindow 必须小于 longWindow" in response.json["error"]["message"]


def test_backtest_rejects_schema_mismatched_parameters() -> None:
    """parameters 必须与策略 info() 声明的 parameterSchema 结构一致。"""
    client, _ = make_client_with_backtest(lambda request: None)

    bad_parameters = [
        {"shortWindow": 5, "longWindow": 20, "evilField": 1},   # 未知字段
        {"shortWindow": 5},                                     # 缺 required 字段
        {},                                                     # 全缺
        {"shortWindow": "5", "longWindow": 20},                 # 类型错误
        {"shortWindow": True, "longWindow": 20},                # bool 伪装整数
        {"shortWindow": 1, "longWindow": 20},                   # 低于 minimum
        {"shortWindow": 5, "longWindow": 3, "extra": 1},        # 缺字段+未知字段
    ]
    for parameters in bad_parameters:
        response = client.post(
            "/api/backtests", json=dict(BACKTEST_BODY, parameters=parameters)
        )
        assert response.status_code == 400, parameters
        assert response.json["error"]["code"] == "VALIDATION_ERROR"

    # 合法参数仍通过
    response = client.post("/api/backtests", json=BACKTEST_BODY)
    assert response.status_code == 202


def test_backtest_momentum_reversal_parameters() -> None:
    """momentum_reversal 的 number 类型参数按 schema 校验。"""
    client, _ = make_client_with_backtest(lambda request: None)

    valid = {
        "symbols": ["510300"],
        "strategyId": "momentum_reversal",
        "parameters": {"lookback": 10, "overboughtThreshold": 5.0, "oversoldThreshold": -5.0},
        "startDate": "2024-01-01",
        "endDate": "2025-12-31",
    }
    assert client.post("/api/backtests", json=valid).status_code == 202

    missing = dict(valid, parameters={"lookback": 10})
    assert client.post("/api/backtests", json=missing).status_code == 400

    bad_type = dict(
        valid,
        parameters={
            "lookback": 10,
            "overboughtThreshold": "5",
            "oversoldThreshold": -5.0,
        },
    )
    assert client.post("/api/backtests", json=bad_type).status_code == 400


def test_backtest_asset_not_in_pool() -> None:
    client, _ = make_client_with_backtest(lambda request: None)
    response = client.post(
        "/api/backtests", json=dict(BACKTEST_BODY, symbols=["999999"])
    )

    assert response.status_code == 404
    assert response.json["error"]["code"] == "ASSET_NOT_FOUND"
def make_ranking_engine_run(returns, nan_strategies=(), calls=None):
    """构造一个可计数的 fake engine.run：按策略返回不同收益，指定策略可给 NaN。"""

    def engine_run(request):

        from pandas import DataFrame
        from quant_platform.models import BacktestMetrics, BacktestResult

        if calls is not None:
            calls.append(request.strategy_id)
        ret = returns.get(request.strategy_id, 0.0)
        sharpe = float("nan") if request.strategy_id in nan_strategies else 1.0
        return BacktestResult(
            metrics=BacktestMetrics(
                total_return_pct=ret,
                annualized_return_pct=ret,
                max_drawdown_pct=2.0,
                sharpe=sharpe,
                alpha_pct=None,
                beta=None,
            ),
            equity_curve=DataFrame(
                {
                    "date": ["2026-08-20"],
                    "equity": [100000.0],
                    "benchmarkEquity": [1.0],
                }
            ),
            trades=(),
            assumptions={},
        )

    return engine_run


def make_client_with_ranking(engine_run, latest_trade_date="2026-08-21"):
    """装配 TESTING app：指定 provider.status 的 latest_trade_date（对齐缓存
    文件状况），替换共享引擎的 run——ranking 的算法层经同一引擎实例调用它。"""
    from datetime import date

    from quant_platform.models import DataStatus

    application = create_app({"TESTING": True})
    provider = application.extensions["market_data_service"]._provider
    provider.status = lambda: DataStatus(
        status="ready",
        source="AkShare",
        asset_count=2,
        latest_trade_date=(
            None if latest_trade_date is None else date.fromisoformat(latest_trade_date)
        ),
        updated_at=None,
        message="test fixture",
    )
    service = application.extensions["ranking_service"]
    service._algorithm._engine.run = engine_run
    return application.test_client()


def test_ranking_matches_contract() -> None:
    client = make_client_with_ranking(
        make_ranking_engine_run({"ma_cross": 5.0, "momentum_reversal": 8.0})
    )

    response = client.get("/api/strategies/ranking")

    assert response.status_code == 200
    body = response.json
    assert body["asOfDate"] == "2026-08-21"
    assert body["period"] == "30d"
    assert [item["strategyId"] for item in body["items"]] == [
        "momentum_reversal",
        "ma_cross",
    ]
    assert [item["rank"] for item in body["items"]] == [1, 2]
    for item in body["items"]:
        assert set(item) == {
            "rank",
            "strategyId",
            "strategyName",
            "category",
            "returnPct",
            "maxDrawdownPct",
            "sharpe",
        }
        assert item["category"] in {"traditional", "ai"}
        assert item["maxDrawdownPct"] >= 0
    assert body["items"][0]["returnPct"] > body["items"][1]["returnPct"]


def test_ranking_period_echo() -> None:
    client = make_client_with_ranking(make_ranking_engine_run({"ma_cross": 1.0}))

    assert client.get("/api/strategies/ranking?period=1y").json["period"] == "1y"
    assert client.get("/api/strategies/ranking?period=7d").json["period"] == "7d"


def test_ranking_rejects_invalid_period() -> None:
    client = make_client_with_ranking(make_ranking_engine_run({}))

    response = client.get("/api/strategies/ranking?period=3d")

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
    assert response.json["error"]["details"] == {"field": "period"}


def test_ranking_upstream_unavailable_when_no_trade_date() -> None:
    client = make_client_with_ranking(
        make_ranking_engine_run({}), latest_trade_date=None
    )

    response = client.get("/api/strategies/ranking")

    assert response.status_code == 503
    assert response.json["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_ranking_insufficient_data_on_nan() -> None:
    """任一指标非有限 → 整体 422，不让残缺条目以 200 出现。"""
    client = make_client_with_ranking(
        make_ranking_engine_run(
            {"ma_cross": 5.0, "momentum_reversal": 8.0},
            nan_strategies=("momentum_reversal",),
        )
    )

    response = client.get("/api/strategies/ranking")

    assert response.status_code == 422
    body = response.json
    assert body["error"]["code"] == "INSUFFICIENT_DATA"
    assert body["error"]["details"] == {
        "period": "30d",
        "strategyId": "momentum_reversal",
        "field": "sharpe",
    }


def _failing_engine_run(request):
    """引擎全失败：算法组 rank 的 except: continue 会吞掉，返回空列表。"""
    raise RuntimeError("engine failed")


def test_ranking_insufficient_data_on_empty_result() -> None:
    """无策略产出真实结果（引擎全失败被算法组吞掉）→ 422，而非 200 空排行。"""
    client = make_client_with_ranking(_failing_engine_run)

    response = client.get("/api/strategies/ranking")

    assert response.status_code == 422
    body = response.json
    assert body["error"]["code"] == "INSUFFICIENT_DATA"
    assert body["error"]["details"] == {"period": "30d", "reason": "rank 返回空"}


def test_ranking_cache_hit_avoids_recompute() -> None:
    calls: list[str] = []
    client = make_client_with_ranking(
        make_ranking_engine_run(
            {"ma_cross": 5.0, "momentum_reversal": 8.0}, calls=calls
        )
    )

    client.get("/api/strategies/ranking")
    client.get("/api/strategies/ranking")

    # 两个策略各算一次；第二次请求命中缓存，不再调用引擎
    assert sorted(calls) == ["ma_cross", "momentum_reversal"]


def test_ranking_single_flight_concurrency() -> None:
    """并发合并：5 个线程同时请求，引擎只被调用一次（每策略一次）。"""
    import threading

    calls: list[str] = []
    client = make_client_with_ranking(
        make_ranking_engine_run(
            {"ma_cross": 5.0, "momentum_reversal": 8.0}, calls=calls
        )
    )
    barrier = threading.Barrier(5)
    statuses: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        response = client.get("/api/strategies/ranking")
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert statuses == [200] * 5
    assert sorted(calls) == ["ma_cross", "momentum_reversal"]


def test_ranking_multi_key_single_flight() -> None:
    """多 key 并发互不覆盖：key1 计算中时 key2 插入，新 key1 请求必须等待合并。

    回归场景（单值 inflight 缺陷）：A 算 key1 时 B 把 inflight 顶成 key2，
    C 再来 key1 会误判"无人算"而重复计算。inflight 改为集合后 C 等待合并。
    """
    import threading
    import time
    from datetime import date

    from quant_platform.models import DataStatus, RankingItem

    from app.services.ranking import RankingService
    from app.services.strategies import StrategyCatalogService

    class TimedRank:
        """fake 算法层：30d 的计算被卡住，直到测试放行；1y 快速返回。"""

        def __init__(self) -> None:
            self.calls: list[str] = []
            self.started_30d = threading.Event()
            self.release_30d = threading.Event()

        def rank(self, *, as_of_date: date, period: str) -> list[RankingItem]:
            self.calls.append(period)
            if period == "30d":
                self.started_30d.set()
                self.release_30d.wait(5)
            return [
                RankingItem(
                    rank=1,
                    strategy_id="ma_cross",
                    strategy_name="均线交叉",
                    category="traditional",
                    return_pct=1.0,
                    max_drawdown_pct=0.5,
                    sharpe=1.0,
                )
            ]

    timed = TimedRank()
    provider = type(
        "P",
        (),
        {
            "status": lambda self: DataStatus(
                status="ready",
                source="AkShare",
                asset_count=1,
                latest_trade_date=date(2026, 8, 21),
                updated_at=None,
                message="",
            )
        },
    )()
    service = RankingService(timed, provider, StrategyCatalogService())

    results: dict[str, object] = {}
    first = threading.Thread(
        target=lambda: results.setdefault("30d", service.get_ranking("30d"))
    )
    first.start()
    assert timed.started_30d.wait(2)  # key1 已开始计算

    results.setdefault("1y", service.get_ranking("1y"))  # key2 插队（主线程）

    late = threading.Thread(
        target=lambda: results.setdefault("30d_late", service.get_ranking("30d"))
    )
    late.start()
    time.sleep(0.2)  # 给 late 进入 _compute 的机会（修复前它会直接开算）

    assert timed.calls.count("30d") == 1  # 关键断言：30d 只算一次

    timed.release_30d.set()
    first.join()
    late.join()
    assert results["30d"] == results["30d_late"]  # 等待者拿到同一份缓存结果

