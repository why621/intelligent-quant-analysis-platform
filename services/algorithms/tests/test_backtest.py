from datetime import date

import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.models import AdjustMode, BacktestRequest, DataStatus, StrategyInfo
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


class RangeIndexStrategy:
    id = "range_index"

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.id,
            name="Range index test strategy",
            category="traditional",
            status="available",
            description="test",
        )

    def validate_parameters(self, parameters):
        pass

    def generate_signals(self, prices, parameters):
        return pd.Series([1.0, -1.0] + [0.0] * (len(prices) - 2))


class ContinuousStrategy:
    """Emits target weights in [0,1]; NaN marks the warm-up region."""

    id = "continuous"

    def __init__(self, signals, band_pct=0.005, min_trade_cny=100.0):
        self._signals = signals
        self.rebalance_band_pct = band_pct
        self.min_trade_cny = min_trade_cny

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.id,
            name="Continuous target strategy",
            category="ai",
            status="experimental",
            description="test",
            signal_semantics="continuous_target_weight",
            requires_trained_model=True,
        )

    def validate_parameters(self, parameters):
        pass

    def generate_signals(self, prices, parameters):
        return pd.Series(self._signals, dtype="float64")


class FixedPriceProvider:
    """Flat OHLC so only target-weight changes drive trades."""

    def __init__(self, close_levels):
        dates = pd.date_range("2025-01-01", periods=len(close_levels), freq="B")
        self._frame = pd.DataFrame({
            "date": dates,
            "open": list(close_levels),
            "high": list(close_levels),
            "low": list(close_levels),
            "close": list(close_levels),
            "volume": [1000.0] * len(close_levels),
            "amount": [10000.0] * len(close_levels),
        })

    def history(self, symbol, start_date, end_date, adjust="qfq"):
        return self._frame.copy()



class InvalidLengthStrategy(RangeIndexStrategy):
    id = "invalid_length"

    def generate_signals(self, prices, parameters):
        return pd.Series([1.0])


class TestBacktest:
    def test_range_index_signals_are_aligned_by_position(self):
        class SmallProvider(FakeProvider):
            def history(self, symbol, start_date, end_date, adjust="qfq"):
                return pd.DataFrame({
                    "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
                    "open": [10.0, 20.0, 30.0],
                    "high": [11.0, 21.0, 31.0],
                    "low": [9.0, 19.0, 29.0],
                    "close": [10.0, 20.0, 30.0],
                    "volume": [1000.0] * 3,
                    "amount": [10000.0] * 3,
                })

        engine = BacktestEngine(SmallProvider(), {"range_index": RangeIndexStrategy()})
        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="range_index",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 3),
        ))

        assert len(result.trades) == 2
        assert result.trades[0].side == "buy"
        assert result.trades[0].price == pytest.approx(20.0 * 1.0002)
        assert result.trades[0].trade_date == date(2025, 1, 2)
        assert result.trades[1].side == "sell"
        assert result.trades[1].price == pytest.approx(30.0 * 0.9998)

        assert result.trades[1].trade_date == date(2025, 1, 3)
    def test_signal_length_must_match_prices(self):
        engine = BacktestEngine(FakeProvider(), {"invalid_length": InvalidLengthStrategy()})

        with pytest.raises(ValueError, match="one value per price row"):
            engine.run(BacktestRequest(
                symbols=("510300",),
                strategy_id="invalid_length",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 3, 31),
            ))

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

    # ---- Step A: continuous target-weight semantics -----------------------

    def _run_continuous(self, signals, levels=None, **kwargs):
        levels = levels or [10.0, 10.0, 10.0, 10.0]
        strategy = ContinuousStrategy(signals, **kwargs)
        engine = BacktestEngine(FixedPriceProvider(levels), {"continuous": strategy})
        return engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="continuous",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            initial_capital_cny=10_000.0,
        ))

    def test_continuous_partial_weight_and_next_open_execution(self):
        # weight 0.5 decided on bar0 close, filled at bar1 open (no look-ahead).
        result = self._run_continuous([0.5, 0.5, 0.5, 0.5])
        assert len(result.trades) == 1
        buy = result.trades[0]
        assert buy.side == "buy"
        # 10.0002 = bar1 open * (1 + slippage 0.02%)
        assert buy.price == pytest.approx(10.0 * 1.0002)
        assert buy.trade_date == date(2025, 1, 2)
        # invested market value ~= half of capital, not all-in
        assert buy.amount_cny == pytest.approx(5000.0, rel=0.01)

    def test_continuous_zero_target_liquidates(self):
        # bar0 -> 0.5 buys at bar1; bar1 -> 0.0 sells everything at bar2.
        result = self._run_continuous([0.5, 0.0, 0.0, 0.0])
        assert [t.side for t in result.trades] == ["buy", "sell"]
        sell = result.trades[1]
        assert sell.price == pytest.approx(10.0 * 0.9998)
        assert sell.trade_date == date(2025, 1, 3)

    def test_continuous_rebalance_band_skips_tiny_changes(self):
        # Flat prices + constant 0.5 target: only the initial buy fires;
        # subsequent deltas fall under the band and churn nothing.
        result = self._run_continuous([0.5, 0.5, 0.5, 0.5])
        assert len(result.trades) == 1

    def test_continuous_warmup_nan_carries_previous_target(self):
        # bar1 is NaN -> forward-filled to 0.5 (hold), NOT a forced liquidation.
        # Only the later drop to 0.25 triggers a partial sell at bar3.
        result = self._run_continuous([0.5, float("nan"), 0.25, 0.25])
        sides = [t.side for t in result.trades]
        assert sides == ["buy", "sell"]
        # the sell happens at bar3 (exec of bar2 decision), not at bar2 (NaN)
        assert result.trades[1].trade_date == date(2025, 1, 6)

    def test_continuous_zero_is_not_discrete_hold(self):
        # Discrete: 0.0 means "hold" -> a buy then two zeros is a single trade.
        discrete = BacktestEngine(
            FixedPriceProvider([10.0, 10.0, 10.0, 10.0]),
            {"range_index": _DiscreteBuyHold()},
        )
        dres = discrete.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="range_index",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            initial_capital_cny=10_000.0,
        ))
        assert [t.side for t in dres.trades] == ["buy"]
        # Continuous: the same [1.0->flat? no] 0 target would sell.
        cres = self._run_continuous([1.0, 0.0, 0.0, 0.0])
        assert [t.side for t in cres.trades] == ["buy", "sell"]

    def test_continuous_assumptions_expose_semantics(self):
        result = self._run_continuous([0.5, 0.5, 0.5, 0.5])
        assert result.assumptions["signalSemantics"] == "continuous_target_weight"
        assert result.assumptions["rebalanceBandPct"] == "0.005"

    def test_per_request_instance_used_when_factory_present(self):
        # A shared strategy exposing create_for_request must be replaced by the
        # fresh instance it returns; the shared one never emits signals.
        class Fresh(RangeIndexStrategy):
            id = "factory"

            def generate_signals(self, prices, parameters):
                return pd.Series([0.0] * len(prices))  # hold -> no trades

        class Shared(RangeIndexStrategy):
            id = "factory"

            def generate_signals(self, prices, parameters):
                return pd.Series([1.0, -1.0] + [0.0] * (len(prices) - 2))  # would trade

            def create_for_request(self, parameters):
                return Fresh()

        engine = BacktestEngine(FakeProvider(), {"factory": Shared()})
        result = engine.run(BacktestRequest(
            symbols=("510300",),
            strategy_id="factory",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ))
        assert result.trades == ()


class _DiscreteBuyHold(RangeIndexStrategy):
    id = "range_index"

    def generate_signals(self, prices, parameters):
        return pd.Series([1.0, 0.0, 0.0, 0.0][: len(prices)])
