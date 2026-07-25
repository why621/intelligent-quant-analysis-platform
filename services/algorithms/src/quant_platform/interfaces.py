"""Protocols implemented by the AkShare, Pandas and strategy modules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

from .models import (
    AdjustMode,
    AllocationSuggestion,
    Asset,
    AssetType,
    BacktestRequest,
    BacktestResult,
    CorrelationRequest,
    CorrelationResult,
    DataStatus,
    RankingItem,
    StrategyInfo,
)

if TYPE_CHECKING:
    import pandas as pd


class MarketDataProvider(Protocol):
    """The only layer allowed to know AkShare-specific APIs and columns."""

    def list_assets(
        self,
        query: str | None = None,
        asset_type: AssetType | None = None,
        limit: int = 50,
    ) -> Sequence[Asset]: ...

    def history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        """Return date/open/high/low/close/volume/amount in date order."""
        ...

    def status(self) -> DataStatus: ...


class Strategy(Protocol):
    id: str

    def info(self) -> StrategyInfo: ...

    def validate_parameters(self, parameters: Mapping[str, object]) -> None: ...

    def generate_signals(
        self,
        prices: pd.DataFrame,
        parameters: Mapping[str, object],
    ) -> pd.Series:
        """Use current and past rows only; return target position or signal."""
        ...


class CorrelationAnalyzer(Protocol):
    def calculate(self, request: CorrelationRequest) -> CorrelationResult: ...


class BacktestEngine(Protocol):
    def run(self, request: BacktestRequest) -> BacktestResult: ...


class StrategyRankingService(Protocol):
    def rank(
        self,
        *,
        as_of_date: date,
        period: Literal["1d", "7d", "30d", "1y"],
    ) -> Sequence[RankingItem]: ...


class AllocationService(Protocol):
    def suggest(
        self,
        *,
        symbols: Sequence[str],
        strategy_id: str,
        cash_pct: float = 0,
    ) -> AllocationSuggestion: ...
