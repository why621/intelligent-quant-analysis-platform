from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    assets: tuple[str, ...]
    strategy: str
    start_date: date
    end_date: date
    params: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.assets:
            raise ValueError("assets must contain at least one symbol")
        if not self.strategy.strip():
            raise ValueError("strategy must not be empty")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    sharpe_ratio: float
    alpha: float
    beta: float
    max_drawdown_pct: float
    total_return_pct: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    request: BacktestRequest
    metrics: BacktestMetrics
    return_series: pd.DataFrame
    drawdown_series: pd.DataFrame


class BacktestEngine(Protocol):
    """Strategy engine boundary implemented by the algorithm group."""

    def run(
        self,
        request: BacktestRequest,
        price_frames: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """Run a reproducible backtest without future-data leakage."""
