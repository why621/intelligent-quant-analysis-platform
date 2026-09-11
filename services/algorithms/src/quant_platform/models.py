"""Framework-independent value objects shared by algorithm implementations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd

AssetType = Literal["stock", "etf"]
AdjustMode = Literal["qfq", "hfq", "none"]
DataState = Literal["ready", "updating", "stale", "failed"]
StrategyCategory = Literal["traditional", "ai"]
StrategyState = Literal["available", "experimental", "planned"]
TradeSide = Literal["buy", "sell"]
AllocationAction = Literal["increase", "hold", "decrease", "exit"]


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    asset_type: AssetType
    exchange: Literal["SSE", "SZSE", "BSE"]
    active: bool = True


@dataclass(frozen=True)
class DataStatus:
    status: DataState
    source: str
    asset_count: int
    latest_trade_date: date | None
    updated_at: datetime | None
    message: str | None = None
    timezone: str = "Asia/Shanghai"
    components: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CorrelationRequest:
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    adjust: AdjustMode = "qfq"
    return_type: Literal["simple", "log"] = "simple"


@dataclass(frozen=True)
class CorrelationResult:
    symbols: tuple[str, ...]
    observation_count: int
    matrix: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class StrategyInfo:
    strategy_id: str
    name: str
    category: StrategyCategory
    status: StrategyState
    description: str
    parameter_schema: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TradingCosts:
    commission_pct: float = 0.03
    stamp_duty_pct: float = 0.05
    slippage_pct: float = 0.02


@dataclass(frozen=True)
class BacktestRequest:
    symbols: tuple[str, ...]
    strategy_id: str
    start_date: date
    end_date: date
    parameters: Mapping[str, object] = field(default_factory=dict)
    benchmark: str | None = None
    initial_capital_cny: float = 100_000.0
    adjust: AdjustMode = "qfq"
    trading_costs: TradingCosts = field(default_factory=TradingCosts)


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    alpha_pct: float | None
    beta: float | None


@dataclass(frozen=True)
class Trade:
    trade_date: date
    symbol: str
    side: TradeSide
    price: float
    quantity: float
    amount_cny: float
    fee_cny: float


@dataclass(frozen=True)
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: pd.DataFrame
    trades: tuple[Trade, ...]
    assumptions: Mapping[str, str]


@dataclass(frozen=True)
class RankingItem:
    rank: int
    strategy_id: str
    strategy_name: str
    category: StrategyCategory
    return_pct: float
    max_drawdown_pct: float
    sharpe: float


@dataclass(frozen=True)
class AllocationPosition:
    symbol: str
    weight_pct: float
    action: AllocationAction
    reason: str


@dataclass(frozen=True)
class AllocationSuggestion:
    basis_date: date
    target_date: date
    strategy_id: str
    positions: tuple[AllocationPosition, ...]
    cash_pct: float
    advisory_only: Literal[True] = True
    disclaimer: str = "仅用于教学研究，不构成投资建议，不会提交真实订单。"
