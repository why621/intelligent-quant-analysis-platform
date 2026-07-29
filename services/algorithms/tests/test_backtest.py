from datetime import date

import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.models import AdjustMode, BacktestRequest, DataStatus
from quant_platform.strategies.ma_cross import MACrossStrategy


class FakeProvider:
    def __init__(self) -> None:
        # 正弦波 + 趋势 = 保证 MA 交叉
        import math
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        trend = pd.Series([100.0 + i * 0.1 for i in range(60)])
        wave = pd.Series([math.sin(i * 0.3) * 3.0 for i in range(60)])
        close = (trend + wave).tolist()
        self._frame = pd.DataFrame({
            "date": dates,
            "open": [c * 0.999 for c in close],
            "high": [c * 1.005 for c in close],
            "low": [c * 0.995 for c in close],
            "close": close,
            "volume": [10000] * 60,
            "amount": [c * 10000 for c in close],
        })
        # 基准：走趋势但不含正弦波
        bm_close = (trend * 1.01).tolist()
        self._bm_frame = pd.DataFrame({
            "date": dates,
            "open": [c * 0.999 for c in bm_close],
            "high": [c * 1.005 for c in bm_close],
            "low": [c * 0.995 for c in bm_close],
            "close": bm_close,
            "volume": [10000] * 60,
            "amount": [c * 10000 for c in bm_close],
        })

    def list_assets(self, query=None, asset_type=None, limit=50):
        return []

    def history(
        self, symbol: str, start_date: date, end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        if symbol == "000300":
            return self._bm_frame.copy()
        if symbol == "510300":
            return self._frame.copy()
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume", "amount"]
        )

    def status(self):
        return DataStatus(status="ready", source="fake", asset_count=1,
                          latest_trade_date=None, updated_at=None)


class TestBacktest:
    def test_run_returns_result_with_metrics(self):
        provider = FakeProvider()
        strategy = MACrossStrategy()
        engine = BacktestEngine(provider, {"ma_cross": strategy})

        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="ma_cross",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            parameters={"shortWindow": 5, "longWindow": 20},
        ))

        m = result.metrics
        assert isinstance(m.total_return_pct, float)
        assert m.max_drawdown_pct >= 0
        assert m.sharpe is not None
        # 无基准时 alpha/beta 为 null
        assert m.alpha_pct is None
        assert m.beta is None

        # 净值曲线包含日期
        assert not result.equity_curve.empty
        assert "date" in result.equity_curve.columns
        assert "equity" in result.equity_curve.columns

        # 假设描述
        assert result.assumptions["signalAt"] == "close"
        assert result.assumptions["executeAt"] == "next_open"

    def test_run_with_benchmark(self):
        provider = FakeProvider()
        strategy = MACrossStrategy()
        engine = BacktestEngine(provider, {"ma_cross": strategy})

        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="ma_cross",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            benchmark="000300",
            parameters={"shortWindow": 5, "longWindow": 20},
        ))

        m = result.metrics
        # benchmark 模式下 metrics 完整，alpha/beta 由数据决定是否有值
        assert isinstance(m.total_return_pct, float)

    def test_unknown_strategy_raises(self):
        provider = FakeProvider()
        engine = BacktestEngine(provider, {})
        with pytest.raises(ValueError, match="未知策略"):
            engine.run(BacktestRequest(
                symbols=("510300",),
                strategy_id="nonexistent",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            ))

    def test_invalid_date_range_raises(self):
        provider = FakeProvider()
        engine = BacktestEngine(provider, {"ma_cross": MACrossStrategy()})
        with pytest.raises(ValueError):
            engine.run(BacktestRequest(
                symbols=("510300",),
                strategy_id="ma_cross",
                start_date=date(2025, 12, 31),
                end_date=date(2025, 1, 1),
            ))

    def test_trades_have_required_fields(self):
        provider = FakeProvider()
        engine = BacktestEngine(provider, {"ma_cross": MACrossStrategy()})
        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="ma_cross",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            parameters={"shortWindow": 5, "longWindow": 20},
        ))

        for t in result.trades:
            assert t.symbol == "510300"
            assert t.side in ("buy", "sell")
            assert t.price > 0
            assert t.quantity > 0
            assert t.amount_cny > 0
            assert t.fee_cny >= 0

    def test_empty_prices_returns_empty_result(self):
        class EmptyProvider(FakeProvider):
            def history(self, symbol, start_date, end_date, adjust="qfq"):
                return pd.DataFrame(
                    columns=["date", "open", "high", "low", "close", "volume", "amount"]
                )

        engine = BacktestEngine(EmptyProvider(), {"ma_cross": MACrossStrategy()})
        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="ma_cross",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ))
        assert result.equity_curve.empty
        assert len(result.trades) == 0
