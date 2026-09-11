from __future__ import annotations

import re
from datetime import date

from flask import Blueprint, current_app, request

from app.services.errors import ServiceError

api = Blueprint("api", __name__)

_RANKING_PERIODS = ("1d", "7d", "30d", "1y")


def error_response(
    *,
    code: str,
    message: str,
    status: int,
    details: dict[str, object] | None = None,
) -> tuple[dict[str, object], int]:
    return (
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
        status,
    )


def pending_response(capability: str) -> tuple[dict[str, object], int]:
    return error_response(
        code="NOT_IMPLEMENTED",
        message="该接口已按统一契约注册，等待对应组员完成实现",
        status=501,
        details={"capability": capability},
    )


def require_json_object() -> tuple[dict[str, object] | None, tuple[dict[str, object], int] | None]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, error_response(
            code="VALIDATION_ERROR",
            message="请求体必须是 JSON 对象",
            status=400,
            details={"field": "body"},
        )
    return payload, None


@api.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "intelligent-quant-backend",
        "version": current_app.config["APP_VERSION"],
    }


@api.get("/data/status")
def data_status() -> tuple[dict[str, object], int]:
    service = current_app.extensions["market_data_service"]
    return dict(service.data_status()), 200


@api.get("/assets")
def list_assets() -> tuple[dict[str, object], int]:
    asset_type = request.args.get("assetType")
    if asset_type is not None and asset_type not in {"stock", "etf"}:
        return error_response(
            code="VALIDATION_ERROR",
            message="assetType 必须是 stock 或 etf",
            status=400,
            details={"field": "assetType"},
        )

    raw_limit = request.args.get("limit", "50")
    if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 100:
        return error_response(
            code="VALIDATION_ERROR",
            message="limit 必须是 1 到 100 的整数",
            status=400,
            details={"field": "limit"},
        )
    limit = int(raw_limit)

    raw_offset = request.args.get("offset", "0")
    if not re.fullmatch(r"[0-9]{1,6}", raw_offset) or int(raw_offset) > 100000:
        return error_response(
            code="VALIDATION_ERROR",
            message="offset 必须是 0 到 100000 的整数",
            status=400,
            details={"field": "offset"},
        )
    offset = int(raw_offset)

    query = request.args.get("query")
    if query is not None and len(query) > 30:
        return error_response(
            code="VALIDATION_ERROR",
            message="query 长度不能超过 30",
            status=400,
            details={"field": "query"},
        )

    service = current_app.extensions["market_data_service"]
    return dict(
        service.list_assets(query=query, asset_type=asset_type, limit=limit, offset=offset)
    ), 200


@api.get("/assets/<string:symbol>/history")
def asset_history(symbol: str) -> tuple[dict[str, object], int]:
    if not re.fullmatch(r"[0-9]{6}", symbol):
        return error_response(
            code="VALIDATION_ERROR",
            message="symbol 必须是六位数字",
            status=400,
            details={"field": "symbol"},
        )

    try:
        start_date = date.fromisoformat(request.args["startDate"])
        end_date = date.fromisoformat(request.args["endDate"])
    except KeyError:
        missing = "startDate" if "startDate" not in request.args else "endDate"
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 和 endDate 为必填参数",
            status=400,
            details={"field": missing},
        )
    except ValueError:
        return error_response(
            code="VALIDATION_ERROR",
            message="日期格式必须是 YYYY-MM-DD",
            status=400,
            details={"field": "startDate"},
        )
    if start_date > end_date:
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 不能晚于 endDate",
            status=400,
            details={"field": "startDate"},
        )

    adjust = request.args.get("adjust", "qfq")
    if adjust not in {"qfq", "hfq", "none"}:
        return error_response(
            code="VALIDATION_ERROR",
            message="adjust 必须是 qfq、hfq 或 none",
            status=400,
            details={"field": "adjust"},
        )

    service = current_app.extensions["market_data_service"]
    try:
        result = service.history(
            symbol=symbol, start_date=start_date, end_date=end_date, adjust=adjust
        )
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.get("/market/overview")
def market_overview() -> tuple[dict[str, object], int]:
    # 忽略 tradeDate 查询参数：只返回最近一次日更的市场概况快照，
    # 响应中的 tradeDate 字段反映数据实际时间。
    service = current_app.extensions["market_data_service"]
    try:
        result = service.market_overview()
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.post("/analytics/correlation")
def correlation() -> tuple[dict[str, object], int]:
    payload, validation_error = require_json_object()
    if validation_error is not None:
        return validation_error

    extra_fields = set(payload) - {"symbols", "startDate", "endDate", "adjust", "returnType"}
    if extra_fields:
        return error_response(
            code="VALIDATION_ERROR",
            message="请求体包含未知字段",
            status=400,
            details={"field": sorted(extra_fields)[0]},
        )

    symbols = payload.get("symbols")
    if (
        not isinstance(symbols, list)
        or not 2 <= len(symbols) <= 10
        or not all(
            isinstance(symbol, str) and re.fullmatch(r"[0-9]{6}", symbol) for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="symbols 必须是 2 到 10 个不同的六位数字资产代码",
            status=400,
            details={"field": "symbols"},
        )

    try:
        start_date = date.fromisoformat(payload["startDate"])
        end_date = date.fromisoformat(payload["endDate"])
    except KeyError:
        missing = "startDate" if "startDate" not in payload else "endDate"
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 和 endDate 为必填字段",
            status=400,
            details={"field": missing},
        )
    except (TypeError, ValueError):
        return error_response(
            code="VALIDATION_ERROR",
            message="日期格式必须是 YYYY-MM-DD",
            status=400,
            details={"field": "startDate"},
        )
    if start_date > end_date:
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 不能晚于 endDate",
            status=400,
            details={"field": "startDate"},
        )

    adjust = payload.get("adjust", "qfq")
    if adjust not in {"qfq", "hfq", "none"}:
        return error_response(
            code="VALIDATION_ERROR",
            message="adjust 必须是 qfq、hfq 或 none",
            status=400,
            details={"field": "adjust"},
        )

    return_type = payload.get("returnType", "simple")
    if return_type not in {"simple", "log"}:
        return error_response(
            code="VALIDATION_ERROR",
            message="returnType 必须是 simple 或 log",
            status=400,
            details={"field": "returnType"},
        )

    service = current_app.extensions["correlation_service"]
    try:
        result = service.calculate(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            return_type=return_type,
        )
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.get("/strategies")
def list_strategies() -> tuple[dict[str, object], int]:
    service = current_app.extensions["strategy_catalog_service"]
    return dict(service.list_strategies()), 200


@api.get("/strategies/ranking")
def strategy_ranking() -> tuple[dict[str, object], int]:
    period = request.args.get("period", "30d")
    if period not in _RANKING_PERIODS:
        return error_response(
            code="VALIDATION_ERROR",
            message=f"period 必须是 {'/'.join(_RANKING_PERIODS)} 之一",
            status=400,
            details={"field": "period"},
        )

    service = current_app.extensions["ranking_service"]
    try:
        result = service.get_ranking(period)
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.post("/backtests")
def create_backtest() -> tuple[dict[str, object], int]:
    payload, validation_error = require_json_object()
    if validation_error is not None:
        return validation_error

    extra_fields = set(payload) - {
        "symbols",
        "strategyId",
        "parameters",
        "startDate",
        "endDate",
        "benchmark",
        "initialCapitalCny",
        "adjust",
        "tradingCosts",
    }
    if extra_fields:
        return error_response(
            code="VALIDATION_ERROR",
            message="请求体包含未知字段",
            status=400,
            details={"field": sorted(extra_fields)[0]},
        )

    symbols = payload.get("symbols")
    if (
        not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 10
        or not all(
            isinstance(symbol, str) and re.fullmatch(r"[0-9]{6}", symbol) for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="symbols 必须是 1 到 10 个不同的六位数字资产代码",
            status=400,
            details={"field": "symbols"},
        )

    strategy_id = payload.get("strategyId")
    if not isinstance(strategy_id, str) or not strategy_id:
        return error_response(
            code="VALIDATION_ERROR",
            message="strategyId 为必填字符串",
            status=400,
            details={"field": "strategyId"},
        )

    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        return error_response(
            code="VALIDATION_ERROR",
            message="parameters 必须是对象",
            status=400,
            details={"field": "parameters"},
        )

    try:
        start_date = date.fromisoformat(payload["startDate"])
        end_date = date.fromisoformat(payload["endDate"])
    except KeyError:
        missing = "startDate" if "startDate" not in payload else "endDate"
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 和 endDate 为必填字段",
            status=400,
            details={"field": missing},
        )
    except (TypeError, ValueError):
        return error_response(
            code="VALIDATION_ERROR",
            message="日期格式必须是 YYYY-MM-DD",
            status=400,
            details={"field": "startDate"},
        )
    if start_date > end_date:
        return error_response(
            code="VALIDATION_ERROR",
            message="startDate 不能晚于 endDate",
            status=400,
            details={"field": "startDate"},
        )

    benchmark = payload.get("benchmark")
    if benchmark is not None and not (
        isinstance(benchmark, str)
        and (re.fullmatch(r"[0-9]{6}", benchmark) or benchmark == "index:CSI:000300")
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="benchmark 必须是六位ETF代码或 index:CSI:000300",
            status=400,
            details={"field": "benchmark"},
        )

    initial_capital = payload.get("initialCapitalCny", 100000)
    if (
        not isinstance(initial_capital, (int, float))
        or isinstance(initial_capital, bool)
        or initial_capital <= 0
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="initialCapitalCny 必须是大于 0 的数字",
            status=400,
            details={"field": "initialCapitalCny"},
        )

    adjust = payload.get("adjust", "qfq")
    if adjust not in {"qfq", "hfq", "none"}:
        return error_response(
            code="VALIDATION_ERROR",
            message="adjust 必须是 qfq、hfq 或 none",
            status=400,
            details={"field": "adjust"},
        )

    trading_costs = payload.get("tradingCosts")
    if trading_costs is not None:
        if not isinstance(trading_costs, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="tradingCosts 必须是对象",
                status=400,
                details={"field": "tradingCosts"},
            )
        extra_cost_fields = set(trading_costs) - {"commissionPct", "stampDutyPct", "slippagePct"}
        if extra_cost_fields:
            return error_response(
                code="VALIDATION_ERROR",
                message="tradingCosts 包含未知字段",
                status=400,
                details={"field": sorted(extra_cost_fields)[0]},
            )
        for field in ("commissionPct", "stampDutyPct", "slippagePct"):
            value = trading_costs.get(field)
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
            ):
                return error_response(
                    code="VALIDATION_ERROR",
                    message=f"{field} 必须是不小于 0 的数字",
                    status=400,
                    details={"field": field},
                )

    service = current_app.extensions["backtest_service"]
    try:
        result = service.submit(payload)
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 202


@api.get("/backtests/<string:job_id>")
def get_backtest(job_id: str) -> tuple[dict[str, object], int]:
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        job_id,
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="jobId 必须是 UUID 格式",
            status=400,
            details={"field": "jobId"},
        )

    service = current_app.extensions["backtest_service"]
    try:
        result = service.get_job(job_id)
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.post("/allocation/suggestion")
def allocation_suggestion() -> tuple[dict[str, object], int]:
    payload, validation_error = require_json_object()
    if validation_error is not None:
        return validation_error

    extra_fields = set(payload) - {"symbols", "strategyId", "cashPct"}
    if extra_fields:
        return error_response(
            code="VALIDATION_ERROR",
            message="请求体包含未知字段",
            status=400,
            details={"field": sorted(extra_fields)[0]},
        )

    symbols = payload.get("symbols")
    if (
        not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 10
        or not all(
            isinstance(symbol, str) and re.fullmatch(r"[0-9]{6}", symbol) for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="symbols 必须是 1 到 10 个不同的六位数字资产代码",
            status=400,
            details={"field": "symbols"},
        )

    strategy_id = payload.get("strategyId")
    if not isinstance(strategy_id, str) or not strategy_id:
        return error_response(
            code="VALIDATION_ERROR",
            message="strategyId 为必填字符串",
            status=400,
            details={"field": "strategyId"},
        )

    cash_pct = payload.get("cashPct", 0)
    if (
        not isinstance(cash_pct, (int, float))
        or isinstance(cash_pct, bool)
        or not 0 <= cash_pct <= 100
    ):
        return error_response(
            code="VALIDATION_ERROR",
            message="cashPct 必须是 0 到 100 的数字",
            status=400,
            details={"field": "cashPct"},
        )

    service = current_app.extensions["allocation_service"]
    try:
        result = service.suggest(
            symbols=symbols,
            strategy_id=strategy_id,
            cash_pct=cash_pct,
        )
    except ServiceError as exc:
        return error_response(
            code=exc.code,
            message=exc.message,
            status=exc.status,
            details=exc.details,
        )
    return dict(result), 200


@api.get("/data/coverage")
def data_coverage():
    from app.services.research_dates import DataNotReadyError, research_read

    provider = current_app.extensions["market_data_service"]._provider
    try:
        if not hasattr(provider, "coverage"):
            raise DataNotReadyError()
        with research_read(provider):
            value = provider.coverage()
        return value, 200
    except ServiceError as exc:
        return error_response(code=exc.code, message=exc.message, status=exc.status)
