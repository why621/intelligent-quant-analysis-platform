from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, current_app, g, request

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
            "code": code,
            "message": message,
            "details": details or {},
            "traceId": g.trace_id,
        },
        status,
    )


def pending_response(capability: str) -> tuple[dict[str, object], int]:
    return error_response(
        code="NOT_IMPLEMENTED",
        message="该接口已经定义，等待对应组员完成实现",
        status=501,
        details={"capability": capability},
    )


@api.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": current_app.config["APP_VERSION"],
        "time": datetime.now(UTC).isoformat(),
    }


@api.get("/market/overview")
def market_overview() -> tuple[dict[str, object], int]:
    return pending_response("market-overview")


@api.post("/analytics/correlation")
def correlation() -> tuple[dict[str, object], int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            code="INVALID_ARGUMENT",
            message="请求体必须是 JSON 对象",
            status=400,
        )
    return pending_response("asset-correlation")


@api.post("/backtests")
def create_backtest() -> tuple[dict[str, object], int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            code="INVALID_ARGUMENT",
            message="请求体必须是 JSON 对象",
            status=400,
        )
    return pending_response("strategy-backtest")


@api.get("/strategies/ranking")
def strategy_ranking() -> tuple[dict[str, object], int]:
    return pending_response("strategy-ranking")


@api.post("/allocation/suggestion")
def allocation_suggestion() -> tuple[dict[str, object], int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response(
            code="INVALID_ARGUMENT",
            message="请求体必须是 JSON 对象",
            status=400,
        )
    return pending_response("allocation-suggestion")
