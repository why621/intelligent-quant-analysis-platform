from __future__ import annotations

from flask import Blueprint, current_app, request

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
    return pending_response("asset-list")


@api.get("/assets/<string:symbol>/history")
def asset_history(symbol: str) -> tuple[dict[str, object], int]:
    return pending_response(f"asset-history:{symbol}")


@api.get("/market/overview")
def market_overview() -> tuple[dict[str, object], int]:
    return pending_response("market-overview")


@api.post("/analytics/correlation")
def correlation() -> tuple[dict[str, object], int]:
    _, validation_error = require_json_object()
    return validation_error or pending_response("asset-correlation")


@api.get("/strategies")
def list_strategies() -> tuple[dict[str, object], int]:
    return pending_response("strategy-list")


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
