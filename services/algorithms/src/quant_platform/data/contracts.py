from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    """Normalized data boundary implemented with AkShare."""

    def stock_history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Return date/open/high/low/close/volume columns sorted by date."""

    def market_overview(self) -> dict[str, object]:
        """Return the MarketOverview response defined in OpenAPI."""
