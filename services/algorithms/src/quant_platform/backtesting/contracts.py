"""Compatibility exports for application-wide backtest contracts."""

from quant_platform.interfaces import BacktestEngine
from quant_platform.models import (
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    Trade,
    TradingCosts,
)

__all__ = [
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestRequest",
    "BacktestResult",
    "Trade",
    "TradingCosts",
]
