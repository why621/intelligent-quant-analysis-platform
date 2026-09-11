from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pandas as pd
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.data.akshare_provider import (
    UpstreamUnavailableError as ProviderUpstreamError,
)

from app.services.errors import AssetNotFoundError, UpstreamUnavailableError
from app.services.research_dates import (
    DataNotReadyError,
    DataVersionChangedError,
    ResearchDateGuard,
    research_context,
    research_read,
)

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
        try:
            context = research_context(self._provider)
            if context["publicationDate"] != _serialize_date(status.latest_trade_date):
                context = None
        except (DataNotReadyError, DataVersionChangedError):
            context = None
        return {
            "benchmarks": (
                [
                    {
                        "assetId": "index:CSI:000300",
                        "name": "沪深300价格指数",
                        "returnBasis": "price_index",
                        "adjust": "none",
                    }
                ]
                if getattr(self._provider, "index_snapshot", None)
                else []
            ),
            "dataContext": context,
            "status": status.status,
            "timezone": status.timezone,
            "source": status.source,
            "assetCount": status.asset_count,
            "latestTradeDate": _serialize_date(status.latest_trade_date),
            "updatedAt": _serialize_datetime(status.updated_at),
            "message": status.message,
            "components": dict(status.components),
        }

    def list_assets(
        self,
        *,
        query: str | None,
        asset_type: str | None,
        limit: int,
        offset: int = 0,
    ) -> Mapping[str, object]:
        """返回资产列表，字段与 contracts/schemas/data.yaml#/Asset 一致。

        total保留本页数量；matchedTotal为过滤后总数。版本仅涵盖目录元数据。
        """
        assets = sorted(
            self._provider.list_assets(limit=None),
            key=lambda asset: (asset.exchange, asset.symbol, asset.asset_type),
        )
        catalog = [
            {
                "assetId": f"{a.asset_type}:{a.exchange}:{a.symbol}",
                "symbol": a.symbol,
                "name": a.name,
                "assetType": a.asset_type,
                "exchange": a.exchange,
                "active": a.active,
            }
            for a in assets
        ]
        version = sha256(
            json.dumps(catalog, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        filtered = catalog
        if query is not None:
            needle = query.strip().lower()
            filtered = [a for a in filtered if needle in a["symbol"] or needle in a["name"].lower()]
        if asset_type is not None:
            filtered = [a for a in filtered if a["assetType"] == asset_type]
        result = filtered[offset : offset + limit]
        end = offset + len(result)
        return {
            "items": result,
            "total": len(result),
            "matchedTotal": len(filtered),
            "offset": offset,
            "nextOffset": end if end < len(filtered) else None,
            "catalogVersion": version,
        }

    def history(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: str,
    ) -> Mapping[str, object]:
        """返回复权日线，字段与 contracts/schemas/data.yaml#/HistoryResponse 一致。

        资产不在池 -> AssetNotFoundError；
        数据源失败且无缓存（provider 抛异常）-> UpstreamUnavailableError；
        区间真无数据 -> 空 items 的 200 响应（provider 返回空 DataFrame）。
        """
        in_pool = any(
            asset.symbol == symbol
            for asset in self._provider.list_assets(query=None, asset_type=None, limit=None)
        )
        if not in_pool:
            raise AssetNotFoundError(details={"symbol": symbol})

        ResearchDateGuard(self._provider).validate([symbol], start_date, end_date)
        try:
            with research_read(self._provider) as context:
                frame = self._provider.history(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                )
        except ProviderUpstreamError as exc:
            raise UpstreamUnavailableError(details={"symbol": symbol}) from exc

        return {
            "dataContext": context,
            "symbol": symbol,
            "adjust": adjust,
            "currency": "CNY",
            "items": [_serialize_price_bar(row) for _, row in frame.iterrows()],
        }

    def market_overview(self) -> Mapping[str, object]:
        """返回市场概况（最新快照），字段与 contracts/schemas/data.yaml#/MarketOverview 一致。

        后端忽略请求中的 tradeDate 查询参数：数据组只维护最近一次日更的快照，
        响应中的 tradeDate 字段如实反映数据的实际时间。
        上游失败（冷缓存且数据源不可用）-> UpstreamUnavailableError。
        """
        try:
            if hasattr(self._provider, "publication_context"):
                with research_read(self._provider):
                    return self._provider.market_overview()
            return self._provider.market_overview()
        except ProviderUpstreamError as exc:
            raise UpstreamUnavailableError(details={"capability": "market-overview"}) from exc


def _serialize_price_bar(row: pd.Series) -> dict[str, object]:
    """把 provider 返回的一行行情翻译成契约 PriceBar（date 转字符串，amount 空值转 null）。"""
    amount = row["amount"]
    return {
        "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
        "amount": None if pd.isna(amount) else float(amount),
    }
