from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Literal

import pandas as pd

from quant_platform.backtesting.engine import BacktestEngine, _compute_metrics
from quant_platform.models import (
    BacktestMetrics,
    BacktestRequest,
    RankingItem,
    StrategyCategory,
)


class StrategyRankingService:
    """日更策略排行。

    对每个可用策略在代表性资产上运行回测，按收益排序。
    仅包含 status=available 的策略，experimental/planned 不进入排行。
    """

    _BENCHMARK_SYMBOL = "510300"

    def __init__(self, engine: BacktestEngine) -> None:
        self._engine = engine

    def rank(
        self,
        *,
        as_of_date: date,
        period: Literal["1d", "7d", "30d", "1y"],
    ) -> list[RankingItem]:
        evaluation_start = _start_date(as_of_date, period)
        request_start = evaluation_start - timedelta(days=90)
        strategy_ids = list(self._engine._strategies.keys())

        results: list[tuple[float, float, float, str, str, StrategyCategory]] = []

        for sid in strategy_ids:
            strategy = self._engine._strategies[sid]
            info = strategy.info()
            if info.status != "available":
                continue

            try:
                result = self._engine.run(BacktestRequest(
                    symbols=(self._BENCHMARK_SYMBOL,),
                    strategy_id=sid,
                    start_date=request_start,
                    end_date=as_of_date,
                ))
                raw_metrics = result.metrics
                if all(math.isfinite(value) for value in (
                    raw_metrics.total_return_pct,
                    raw_metrics.max_drawdown_pct,
                    raw_metrics.sharpe,
                )):
                    metrics = _period_metrics(
                        result.equity_curve, as_of_date, period
                    )
                else:
                    metrics = raw_metrics
            except Exception:
                continue

            results.append((
                metrics.total_return_pct,
                metrics.max_drawdown_pct,
                metrics.sharpe,
                sid,
                info.name,
                info.category,
            ))

        results.sort(key=lambda x: x[0], reverse=True)

        return [
            RankingItem(
                rank=i + 1,
                strategy_id=sid,
                strategy_name=name,
                category=cat,
                return_pct=ret,
                max_drawdown_pct=mdd,
                sharpe=sh,
            )
            for i, (ret, mdd, sh, sid, name, cat) in enumerate(results)
        ]


def _start_date(as_of: date, period: str) -> date:
    return {
        "1d": as_of - timedelta(days=1),
        "7d": as_of - timedelta(days=7),
        "30d": as_of - timedelta(days=30),
        "1y": as_of - timedelta(days=365),
    }[period]


def _period_metrics(
    curve: pd.DataFrame,
    as_of_date: date,
    period: Literal["1d", "7d", "30d", "1y"],
) -> BacktestMetrics:
    if curve.empty:
        return _compute_metrics(pd.Series(dtype=float), None, 1.0)

    prepared = curve[["date", "equity"]].dropna().copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared = prepared.sort_values("date").drop_duplicates("date", keep="last")
    if prepared.empty:
        return _compute_metrics(pd.Series(dtype=float), None, 1.0)

    if period == "1d":
        window = prepared.tail(2)
    else:
        start = pd.Timestamp(_start_date(as_of_date, period))
        window = prepared[prepared["date"] >= start]
        if window.empty:
            window = prepared.tail(1)

    equity = pd.Series(
        window["equity"].to_numpy(dtype=float),
        index=pd.DatetimeIndex(window["date"]),
        dtype=float,
    )
    return _compute_metrics(equity, None, float(equity.iloc[0]))
