from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import pandas as pd


class MarketDataService(Protocol):
    """Boundary implemented by the AkShare/Pandas data layer."""

    def data_status(self) -> Mapping[str, object]:
        """Return DataStatus from the OpenAPI contract."""

    def list_assets(
        self,
        *,
        query: str | None,
        asset_type: str | None,
        limit: int,
    ) -> Sequence[Mapping[str, object]]:
        """Return only assets in the maintained A-share/ETF universe."""

    def history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> pd.DataFrame:
        """Return date/open/high/low/close/volume/amount in ascending order."""

    def market_overview(self, *, trade_date: str | None) -> Mapping[str, object]:
        """Return MarketOverview for an actual trading date."""


class StrategyCatalogService(Protocol):
    def list_strategies(self) -> Sequence[Mapping[str, object]]:
        """Return available, experimental and planned strategy metadata."""

    def ranking(self, *, period: str) -> Mapping[str, object]:
        """Return genuinely evaluated, persisted results only."""


class AnalyticsService(Protocol):
    def correlation(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Return CorrelationResponse after contract validation."""

    def allocation_suggestion(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Return next-trading-day advisory allocation."""


class BacktestJobService(Protocol):
    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Create a job and return BacktestJob with queued status."""

    def get(self, *, job_id: str) -> Mapping[str, object]:
        """Return current status and result/error for one job."""
