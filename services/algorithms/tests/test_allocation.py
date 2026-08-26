from datetime import date

import pandas as pd

from quant_platform.allocation import AllocationService
from quant_platform.models import (
    AdjustMode,
    DataStatus,
    StrategyInfo,
)


class FakeProvider:
    def history(
        self, symbol: str, start_date: date, end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        dates = pd.date_range(start_date, periods=30, freq="B")
        # 不同 symbol 产生不同信号：
        # sym1 持续上涨 → MACross 可能买入
        # sym2 持续下跌 → 可能卖出
        if symbol == "sym1":
            close = [100.0 + i * 0.5 for i in range(30)]
        elif symbol == "sym2":
            close = [100.0 - i * 0.5 for i in range(30)]
        else:
            close = [100.0 + i * 0.1 for i in range(30)]
        return pd.DataFrame({
            "date": dates,
            "open": [c * 0.999 for c in close],
            "high": [c * 1.005 for c in close],
            "low": [c * 0.995 for c in close],
            "close": close,
            "volume": [10000] * 30,
            "amount": [c * 10000 for c in close],
        })

    def list_assets(self, query=None, asset_type=None, limit=50):
        return []

    def status(self):
        return DataStatus(status="ready", source="fake", asset_count=3,
                          latest_trade_date=None, updated_at=None)

    def market_overview(self, trade_date=None):
        return {}


class FakeStrategy:
    """根据最近收盘价变化自动生成信号。"""
    id = "test_strategy"

    def info(self):
        return StrategyInfo(
            strategy_id=self.id,
            name="测试策略",
            category="traditional",
            status="available",
            description="",
        )

    def validate_parameters(self, p):
        pass

    def generate_signals(self, prices, parameters):
        # 最后一天涨 → 买入，跌 → 卖出
        close = prices["close"].astype(float)
        ret = close.iloc[-1] - close.iloc[-2] if len(close) >= 2 else 0
        sig = pd.Series(0, index=prices.index, dtype=float)
        if ret > 0:
            sig.iloc[-1] = 1.0
        elif ret < 0:
            sig.iloc[-1] = -1.0
        return sig


class TestAllocation:
    def test_weights_sum_to_100_minus_cash(self):
        provider = FakeProvider()
        svc = AllocationService(provider, {"test_strategy": FakeStrategy()})

        suggestion = svc.suggest(
            symbols=["sym1", "sym2"],
            strategy_id="test_strategy",
            cash_pct=10,
        )

        total = sum(p.weight_pct for p in suggestion.positions) + suggestion.cash_pct
        assert abs(total - 100.0) < 0.01
        assert suggestion.advisory_only is True

    def test_increase_signal_gets_positive_weight(self):
        provider = FakeProvider()
        svc = AllocationService(provider, {"test_strategy": FakeStrategy()})

        suggestion = svc.suggest(
            symbols=["sym1"],  # 上涨
            strategy_id="test_strategy",
            cash_pct=0,
        )

        assert len(suggestion.positions) == 1
        assert suggestion.positions[0].action == "increase"
        assert suggestion.positions[0].weight_pct > 0

    def test_exit_signal_gets_zero_weight(self):
        provider = FakeProvider()
        svc = AllocationService(provider, {"test_strategy": FakeStrategy()})

        suggestion = svc.suggest(
            symbols=["sym2"],  # 下跌
            strategy_id="test_strategy",
            cash_pct=0,
        )

        assert len(suggestion.positions) == 1
        assert suggestion.positions[0].action == "exit"
        assert suggestion.positions[0].weight_pct == 0.0

    def test_unknown_strategy_raises(self):
        provider = FakeProvider()
        svc = AllocationService(provider, {})

        with __import__("pytest").raises(ValueError, match="未知策略"):
            svc.suggest(symbols=["sym1"], strategy_id="nosuch")

    def test_returns_correct_field_types(self):
        provider = FakeProvider()
        svc = AllocationService(provider, {"test_strategy": FakeStrategy()})

        suggestion = svc.suggest(symbols=["sym1"], strategy_id="test_strategy", cash_pct=0)

        assert isinstance(suggestion.basis_date, date)
        assert isinstance(suggestion.target_date, date)
        assert suggestion.target_date > suggestion.basis_date
        assert suggestion.strategy_id == "test_strategy"
        assert "不构成投资建议" in suggestion.disclaimer

    def test_empty_prices_handled_gracefully(self):
        class EmptyProvider(FakeProvider):
            def history(self, symbol, start_date, end_date, adjust="qfq"):
                return pd.DataFrame(
                    columns=["date", "open", "high", "low", "close", "volume", "amount"]
                )

        provider = EmptyProvider()
        svc = AllocationService(provider, {"test_strategy": FakeStrategy()})

        suggestion = svc.suggest(symbols=["sym1"], strategy_id="test_strategy", cash_pct=0)
        assert len(suggestion.positions) == 1
        assert suggestion.positions[0].action == "hold"
