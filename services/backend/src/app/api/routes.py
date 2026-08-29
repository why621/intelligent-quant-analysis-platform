from __future__ import annotations

import re
from datetime import date

from flask import Blueprint, current_app, request

from app.services.errors import ServiceError

api = Blueprint("api", __name__)


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

    query = request.args.get("query")
    if query is not None and len(query) > 30:
        return error_response(
            code="VALIDATION_ERROR",
            message="query 长度不能超过 30",
            status=400,
            details={"field": "query"},
        )

    service = current_app.extensions["market_data_service"]
    return dict(service.list_assets(query=query, asset_type=asset_type, limit=limit)), 200


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
    _, validation_error = require_json_object()
    return validation_error or pending_response("asset-correlation")


@api.get("/strategies")
def list_strategies() -> tuple[dict[str, object], int]:
    service = current_app.extensions["strategy_catalog_service"]
    return dict(service.list_strategies()), 200


@api.get("/strategies/ranking")
def strategy_ranking() -> tuple[dict[str, object], int]:
    return pending_response("strategy-ranking")


@api.post("/backtests")
def create_backtest() -> tuple[dict[str, object], int]:
    _, validation_error = require_json_object()
    return validation_error or pending_response("backtest-submit")


@api.get("/backtests/<string:job_id>")
def get_backtest(job_id: str) -> tuple[dict[str, object], int]:
    return pending_response(f"backtest-result:{job_id}")


@api.post("/allocation/suggestion")
def allocation_suggestion() -> tuple[dict[str, object], int]:
    _, validation_error = require_json_object()
    return validation_error or pending_response("allocation-suggestion")
