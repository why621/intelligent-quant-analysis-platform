from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import pandas as pd


class MarketDataService(Protocol):
    """Boundary the AkShare implementation must satisfy."""

    def market_overview(self) -> dict[str, object]:
        """Return the response defined by MarketOverview in OpenAPI."""

    def history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Return normalized date/open/high/low/close/volume columns."""


class AnalyticsService(Protocol):
    """Boundary between Flask routes and the algorithm package."""

    def correlation(
        self,
        *,
        assets: Sequence[str],
        window_days: int,
    ) -> dict[str, object]:
        """Return the response defined by CorrelationResponse in OpenAPI."""

    def run_backtest(self, payload: dict[str, object]) -> dict[str, object]:
        """Return the response defined by BacktestResponse in OpenAPI."""

    def strategy_ranking(self) -> dict[str, object]:
        """Return the response defined by StrategyRankingResponse in OpenAPI."""

    def allocation_suggestion(self, payload: dict[str, object]) -> dict[str, object]:
        """Return the response defined by AllocationResponse in OpenAPI."""
