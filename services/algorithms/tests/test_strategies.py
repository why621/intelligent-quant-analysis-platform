import pandas as pd
import pytest

from quant_platform.strategies.ma_cross import MACrossStrategy
from quant_platform.strategies.momentum_reversal import MomentumReversalStrategy


def _fake_prices(length: int = 60) -> pd.DataFrame:
    """生成递增收盘价的简单 DataFrame，用于验证信号逻辑。"""
    dates = pd.date_range("2025-01-01", periods=length, freq="B")
    close = list(range(10, 10 + length))
    return pd.DataFrame({"date": dates, "close": close}, index=dates)


# ---------------------------------------------------------------------------
# ma_cross
# ---------------------------------------------------------------------------


class TestMACross:
    def test_info_returns_available_strategy(self):
        s = MACrossStrategy()
        info = s.info()
        assert info.strategy_id == "ma_cross"
        assert info.status == "available"
        assert "shortWindow" in info.parameter_schema["properties"]

    def test_validate_rejects_short_ge_long(self):
        s = MACrossStrategy()
        with pytest.raises(ValueError):
            s.validate_parameters({"shortWindow": 20, "longWindow": 5})

    def test_validate_rejects_negative_window(self):
        s = MACrossStrategy()
        with pytest.raises(ValueError):
            s.validate_parameters({"shortWindow": 1, "longWindow": 20})

    def test_generate_signals_returns_int_series(self):
        s = MACrossStrategy()
        df = _fake_prices(60)
        signals = s.generate_signals(df, {"shortWindow": 5, "longWindow": 20})
        assert isinstance(signals, pd.Series)
        assert signals.isin([-1.0, 0.0, 1.0]).all()

    def test_generate_signals_empty_returns_empty(self):
        s = MACrossStrategy()
        signals = s.generate_signals(pd.DataFrame(), {"shortWindow": 5, "longWindow": 20})
        assert signals.empty


# ---------------------------------------------------------------------------
# momentum_reversal
# ---------------------------------------------------------------------------


class TestMomentumReversal:
    def test_info_returns_available_strategy(self):
        s = MomentumReversalStrategy()
        info = s.info()
        assert info.strategy_id == "momentum_reversal"
        assert info.status == "available"
        assert "lookback" in info.parameter_schema["properties"]

    def test_validate_rejects_overbought_le_oversold(self):
        s = MomentumReversalStrategy()
        with pytest.raises(ValueError):
            s.validate_parameters({
                "lookback": 10,
                "overboughtThreshold": 3.0,
                "oversoldThreshold": 5.0,
            })

    def test_validate_rejects_small_lookback(self):
        s = MomentumReversalStrategy()
        with pytest.raises(ValueError):
            s.validate_parameters({
                "lookback": 1,
                "overboughtThreshold": 5.0,
                "oversoldThreshold": -5.0,
            })

    def test_generate_signals_returns_int_series(self):
        s = MomentumReversalStrategy()
        df = _fake_prices(100)
        signals = s.generate_signals(df, {
            "lookback": 10,
            "overboughtThreshold": 5.0,
            "oversoldThreshold": -5.0,
        })
        assert isinstance(signals, pd.Series)
        # 持续上涨：warmup 期后全部触发超买（卖出信号）
        assert (signals.iloc[20:] == -1.0).all()

    def test_generate_signals_buy_on_oversold(self):
        s = MomentumReversalStrategy()
        # 构造先大跌后横盘的数据：前期 lookback 窗口内大幅下跌 → 触发超卖
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        close_vals = [100.0] * 10 + [50.0] * 50  # 第 10 天后暴跌
        df = pd.DataFrame({"date": dates, "close": close_vals}, index=dates)
        signals = s.generate_signals(df, {
            "lookback": 10,
            "overboughtThreshold": 30.0,
            "oversoldThreshold": -30.0,
        })
        assert 1.0 in signals.values

    def test_generate_signals_empty_returns_empty(self):
        s = MomentumReversalStrategy()
        signals = s.generate_signals(pd.DataFrame(), {"lookback": 10})
        assert signals.empty
