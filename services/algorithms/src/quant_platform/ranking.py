from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.models import (
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
        start = _start_date(as_of_date, period)
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
                    start_date=start,
                    end_date=as_of_date,
                ))
            except Exception:
                continue

            results.append((
                result.metrics.total_return_pct,
                result.metrics.max_drawdown_pct,
                result.metrics.sharpe,
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
        "1d": as_of - timedelta(days=30),
        "7d": as_of - timedelta(days=7),
        "30d": as_of - timedelta(days=30),
        "1y": as_of - timedelta(days=365),
    }[period]
