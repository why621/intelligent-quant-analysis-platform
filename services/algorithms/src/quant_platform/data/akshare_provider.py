from __future__ import annotations

import pandas as pd


class AkShareMarketDataProvider:
    """Implementation slot owned by the market-data/algorithm group."""

    def stock_history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "Use akshare.stock_zh_a_hist and normalize its columns to the provider contract"
        )

    def market_overview(self) -> dict[str, object]:
        raise NotImplementedError(
            "Select authorized AkShare endpoints and map them to the OpenAPI MarketOverview schema"
        )
