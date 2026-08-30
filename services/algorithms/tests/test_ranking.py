from datetime import date

import pandas as pd
import pytest

from quant_platform.models import (
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    StrategyCategory,
    StrategyInfo,
)
from quant_platform.ranking import StrategyRankingService, _period_metrics


class FakeStrategy:
    def __init__(self, sid: str, name: str, status: str, category: StrategyCategory):
        self.id = sid
        self._name = name
        self._status = status
        self._category = category

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.id,
            name=self._name,
            category=self._category,
            status=self._status,  # type: ignore[arg-type]
            description="test",
        )

    def validate_parameters(self, p):
        pass

    def generate_signals(self, prices, p):
        return pd.Series(dtype=float)


class FakeEngine:
    def __init__(self, strategies: dict):
        self._strategies = strategies
        self.requests: list[BacktestRequest] = []

    def run(self, request: BacktestRequest) -> BacktestResult:
        self.requests.append(request)
        ret = {"ma_cross": 5.0, "momentum_reversal": 12.0, "a": 3.0,
               "b": 8.0, "c": 1.0, "dqn": 3.0, "experiment": 2.0}.get(
            request.strategy_id, 0.0)
        dates = pd.date_range(request.start_date, request.end_date, freq="B")
        return BacktestResult(
            metrics=BacktestMetrics(
                total_return_pct=ret,
                annualized_return_pct=ret,
                max_drawdown_pct=2.0,
                sharpe=1.5,
                alpha_pct=None,
                beta=None,
            ),
            equity_curve=pd.DataFrame({
                "date": dates,
                "equity": [1.0] * (len(dates) - 1) + [1.0 + ret / 100],
                "benchmarkEquity": [1.0] * len(dates),
            }),
            trades=(),
            assumptions={"signalAt": "close", "executeAt": "next_open",
                         "calendar": "CN", "currency": "CNY"},
        )


class TestRanking:
    def test_ranks_descending_by_return(self):
        strategies = {
            "ma_cross": FakeStrategy(
                "ma_cross", "均线交叉", "available", "traditional"
            ),
            "momentum_reversal": FakeStrategy(
                "momentum_reversal", "动量反转", "available", "traditional"
            ),
        }
        engine = FakeEngine(strategies)
        svc = StrategyRankingService(engine)

        items = svc.rank(as_of_date=date(2025, 12, 31), period="30d")

        assert len(items) == 2
        assert items[0].strategy_id == "momentum_reversal"  # 12 > 5
        assert items[0].rank == 1
        assert items[1].strategy_id == "ma_cross"
        assert items[1].rank == 2
        for it in items:
            assert it.return_pct is not None
            assert it.max_drawdown_pct is not None
            assert it.sharpe is not None

    def test_excludes_non_available_strategies(self):
        strategies = {
            "ma_cross": FakeStrategy("ma_cross", "均线交叉", "available", "traditional"),
            "dqn": FakeStrategy("dqn", "DQN", "planned", "ai"),
            "experiment": FakeStrategy("experiment", "实验策略", "experimental", "ai"),
        }
        engine = FakeEngine(strategies)
        svc = StrategyRankingService(engine)

        items = svc.rank(as_of_date=date(2025, 12, 31), period="30d")

        assert len(items) == 1
        assert items[0].strategy_id == "ma_cross"

    def test_empty_when_no_available_strategies(self):
        strategies = {
            "dqn": FakeStrategy("dqn", "DQN", "planned", "ai"),
        }
        engine = FakeEngine(strategies)
        svc = StrategyRankingService(engine)

        items = svc.rank(as_of_date=date(2025, 12, 31), period="30d")
        assert items == []

    def test_one_day_period_uses_warmup_and_two_trading_sessions(self):
        strategies = {
            "ma_cross": FakeStrategy("ma_cross", "均线交叉", "available", "traditional"),
        }
        engine = FakeEngine(strategies)
        items = StrategyRankingService(engine).rank(
            as_of_date=date(2025, 12, 31), period="1d"
        )

        assert len(engine.requests) == 1
        assert engine.requests[0].start_date == date(2025, 10, 1)
        assert engine.requests[0].end_date == date(2025, 12, 31)
        assert items[0].return_pct == pytest.approx(5.0)

    def test_correct_rank_numbers(self):
        strategies = {
            "a": FakeStrategy("a", "A", "available", "traditional"),
            "b": FakeStrategy("b", "B", "available", "traditional"),
            "c": FakeStrategy("c", "C", "available", "traditional"),
        }
        engine = FakeEngine(strategies)
        svc = StrategyRankingService(engine)

        items = svc.rank(as_of_date=date(2025, 12, 31), period="1y")

        ranks = [it.rank for it in items]
        assert ranks == [1, 2, 3]

def test_period_metrics_exclude_warmup_history():
    curve = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-10-01", "2025-11-30", "2025-12-01", "2025-12-31"]
            ),
            "equity": [1.0, 2.0, 2.0, 2.2],
        }
    )

    metrics = _period_metrics(curve, date(2025, 12, 31), "30d")

    assert metrics.total_return_pct == pytest.approx(10.0)
