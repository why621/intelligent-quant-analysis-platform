from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta
from typing import Literal

import pandas as pd

from quant_platform.backtesting.engine import BacktestEngine, _compute_metrics
from quant_platform.models import BacktestMetrics, BacktestRequest, RankingItem


class RankingResult(list[RankingItem]):
    """List-compatible result with request-local exclusion diagnostics."""

    def __init__(self, items=(), *, unavailable=()):
        super().__init__(items)
        self.unavailable = tuple(unavailable)


class StrategyRankingService:
    """Rank traditional strategies and explicitly deployed experimental models."""

    _BENCHMARK_SYMBOL = "510300"

    def __init__(self, engine: BacktestEngine) -> None:
        self._engine = engine

    def rank(self, *, as_of_date: date, period: Literal["1d", "7d", "30d", "1y"]) -> RankingResult:
        request_start = _start_date(as_of_date, period) - timedelta(days=90)
        results = []
        unavailable = []
        for sid, strategy in self._engine._strategies.items():
            info = strategy.info()
            deployed = (
                info.status == "experimental"
                and getattr(strategy, "ranking_enabled", False) is True
                and callable(getattr(strategy, "ranking_request", None))
            )
            if not deployed and (info.status != "available" or info.requires_trained_model):
                continue
            try:
                request = (
                    strategy.ranking_request(as_of_date, period, self._engine._provider)
                    if deployed
                    else BacktestRequest(
                        symbols=(self._BENCHMARK_SYMBOL,),
                        strategy_id=sid,
                        start_date=request_start,
                        end_date=as_of_date,
                    )
                )
                result = self._engine.run(request)
                raw = result.metrics
                metrics = (
                    _period_metrics(result.equity_curve, as_of_date, period)
                    if all(
                        math.isfinite(x)
                        for x in (raw.total_return_pct, raw.max_drawdown_pct, raw.sharpe)
                    )
                    else raw
                )
                context = strategy.model_context() if deployed else None
                results.append(
                    RankingItem(
                        rank=0,
                        strategy_id=sid,
                        strategy_name=info.name,
                        category=info.category,
                        return_pct=metrics.total_return_pct,
                        max_drawdown_pct=metrics.max_drawdown_pct,
                        sharpe=metrics.sharpe,
                        status=info.status,
                        model_context=context,
                    )
                )
            except Exception as exc:
                code = getattr(exc, "code", "RANKING_FAILED")
                message = {
                    "RL_IN_SAMPLE_REQUEST": "该区间与训练期重叠，未参与排行",
                    "RL_INSUFFICIENT_HISTORY": "样本外历史不足以完成预热并覆盖评价区间",
                    "RL_INCOMPATIBLE_MODEL": "模型版本或完整性不匹配，未参与排行",
                    "RL_MODEL_NOT_FOUND": "已部署模型不可用，未参与排行",
                    "RL_DEPENDENCIES_MISSING": "模型运行依赖不可用，未参与排行",
                }.get(code, "策略计算失败，未参与排行")
                unavailable.append(
                    {"strategyId": sid, "strategyName": info.name, "code": code, "message": message}
                )
        results.sort(key=lambda item: item.return_pct, reverse=True)
        return RankingResult(
            (replace(item, rank=i + 1) for i, item in enumerate(results)), unavailable=unavailable
        )


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
