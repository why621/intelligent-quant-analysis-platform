import json
from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from datetime import date
from hashlib import sha256

from flask import has_request_context, request
from quant_platform.data.coverage import digest

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
        available_start = getattr(self._provider, "start", date(2025, 1, 1))
        details = {
            "field": "endDate",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "availableStartDate": available_start.isoformat(),
            "availableEndDate": available_end.isoformat() if available_end else None,
            "symbols": list(symbols),
        }
        if cutoff is None or history_state in {"failed", "updating"}:
            raise DataNotReadyError(details=details)
        if start < available_start or end > available_end:
            details["field"] = "startDate" if start < available_start else "endDate"
            raise DateOutOfRangeError(
                message=(f"请求日期超出可用范围 {available_start.isoformat()} "
                         f"至 {available_end.isoformat()}"),
                details=details,
            )


class DataVersionChangedError(ServiceError):
    code = "DATA_VERSION_CHANGED"
    status = 409
    message = "数据版本已更新，请刷新数据状态后重新提交研究"


def research_context(provider):
    """Describe a legacy cache revision honestly; this is not an immutable release."""
    if hasattr(provider, "publication_context"):
        return provider.publication_context
    before = (
        str(provider.cache_revision()) if hasattr(provider, "cache_revision") else "unversioned"
    )
    status = provider.status()
    state = status.components.get("history", {}).get("status", status.status)
    if status.latest_trade_date is None or state in {"failed", "updating"}:
        raise DataNotReadyError()
    assets = provider.list_assets(limit=None) if hasattr(provider, "list_assets") else []
    catalog = sorted((a.asset_type, a.exchange, a.symbol, a.name, a.active) for a in assets)
    snapshot = getattr(provider, "universe_snapshot", None)
    universe = (snapshot.to_dict()["snapshotId"] if snapshot is not None else None) or sha256(
        json.dumps(catalog, ensure_ascii=False).encode()
    ).hexdigest()
    after = str(provider.cache_revision()) if hasattr(provider, "cache_revision") else "unversioned"
    if before != after:
        raise DataVersionChangedError()
    index = getattr(provider, "index_snapshot", None)
    index_version = index.to_dict()["snapshotId"] if index else None
    value = {
        "publicationDate": status.latest_trade_date.isoformat(),
        "universeVersion": universe,
        "consistency": "legacy_revision",
    }
    value["dataVersion"] = sha256(
        json.dumps(
            [
                value,
                before,
                index_version,
                digest([e.to_dict() for e in getattr(provider, "trading_events", ())]),
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return value


@contextmanager
def research_read(provider, expected=None):
    context = research_context(provider)
    requested = request.headers.get("X-Research-Version") if has_request_context() else None
    if (expected is not None and context != expected) or (
        requested and requested != context["dataVersion"]
    ):
        raise DataVersionChangedError()
    reader = getattr(provider, "read_only_research", None)
    scope = reader(date.fromisoformat(context["publicationDate"])) if reader else nullcontext()
    with scope:
        yield context
    try:
        changed = research_context(provider) != context
    except DataNotReadyError:
        changed = True
    if changed:
        raise DataVersionChangedError()
