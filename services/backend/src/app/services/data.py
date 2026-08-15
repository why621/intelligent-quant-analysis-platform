from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from zoneinfo import ZoneInfo

from quant_platform.data.akshare_provider import AkShareMarketDataProvider

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # provider 用 datetime.now() 产生 naive 时间，契约要求带业务时区
        value = value.replace(tzinfo=SHANGHAI)
    return value.isoformat()


class MarketDataService:
    """数据类接口的实现：调用算法组数据提供者并翻译为契约 JSON。

    路由层只做解析、校验和序列化，不直接接触 AkShare。
    """

    def __init__(self, provider: AkShareMarketDataProvider) -> None:
        self._provider = provider

    def data_status(self) -> Mapping[str, object]:
        """返回日更数据状态，字段与 contracts/schemas/data.yaml#/DataStatus 一致。"""
        status = self._provider.status()
        return {
            "status": status.status,
            "timezone": status.timezone,
            "source": status.source,
            "assetCount": status.asset_count,
            "latestTradeDate": _serialize_date(status.latest_trade_date),
            "updatedAt": _serialize_datetime(status.updated_at),
            "message": status.message,
        }
