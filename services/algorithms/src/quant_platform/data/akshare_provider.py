from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.models import AdjustMode, Asset, AssetType, DataStatus


class AkShareMarketDataProvider:
    """Implementation slot owned by the market-data/algorithm group."""

    def list_assets(
        self,
        query: str | None = None,
        asset_type: AssetType | None = None,
        limit: int = 50,
    ) -> list[Asset]:
        raise NotImplementedError("Load the maintained 30–50 asset A-share/ETF universe")

    def history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Use AkShare A-share/ETF history APIs and normalize columns to the contract"
        )

    def stock_history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Deprecated compatibility entry point; new code should call history."""
        return self.history(
            symbol,
            date.fromisoformat(start_date),
            date.fromisoformat(end_date),
            adjust,  # type: ignore[arg-type]
        )

    def status(self) -> DataStatus:
        raise NotImplementedError("Return the persisted end-of-day update status")

    def market_overview(self) -> dict[str, object]:
        raise NotImplementedError("Map authorized AkShare data to MarketOverview")
