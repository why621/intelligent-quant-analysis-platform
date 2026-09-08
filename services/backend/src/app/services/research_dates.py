from collections.abc import Sequence
from datetime import date

from app.services.errors import ServiceError


class DataNotReadyError(ServiceError):
    code = "DATA_NOT_READY"
    status = 503
    message = "历史数据尚无可用发布状态，请等待数据更新"


class DateOutOfRangeError(ServiceError):
    code = "DATE_OUT_OF_RANGE"
    status = 400


class ResearchDateGuard:
    """Check publication bounds without fetching prices or claiming per-asset coverage."""

    def __init__(self, provider):
        self._provider = provider

    def validate(self, symbols: Sequence[str], start: date, end: date) -> None:
        status = self._provider.status()
        cutoff = status.latest_trade_date
        history_state = status.components.get("history", {}).get("status", status.status)
        available_end = min(cutoff, date(2026, 12, 31)) if cutoff else None
        details = {
            "field": "endDate",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "availableStartDate": "2025-01-01",
            "availableEndDate": available_end.isoformat() if available_end else None,
            "symbols": list(symbols),
        }
        if cutoff is None or history_state == "failed":
            raise DataNotReadyError(details=details)
        if start < date(2025, 1, 1) or end > available_end:
            details["field"] = "startDate" if start < date(2025, 1, 1) else "endDate"
            raise DateOutOfRangeError(
                message=f"请求日期超出可用范围 2025-01-01 至 {available_end.isoformat()}",
                details=details,
            )
