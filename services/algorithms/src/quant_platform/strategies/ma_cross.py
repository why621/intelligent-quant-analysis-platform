from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from quant_platform.models import StrategyInfo


class MACrossStrategy:
    """均线交叉策略：短均线上穿长均线买入 (1)，下穿卖出 (-1)。"""

    id: str = "ma_cross"

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.id,
            name="均线交叉",
            category="traditional",
            status="available",
            description="短均线上穿长均线产生买入信号，下穿产生卖出信号。"
            "收盘生成信号，下一交易日开盘成交。",
            parameter_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["shortWindow", "longWindow"],
                "properties": {
                    "shortWindow": {
                        "type": "integer",
                        "minimum": 2,
                        "default": 5,
                        "description": "短期均线窗口",
                    },
                    "longWindow": {
                        "type": "integer",
                        "minimum": 3,
                        "default": 20,
                        "description": "长期均线窗口",
                    },
                },
            },
        )

    def validate_parameters(self, parameters: Mapping[str, object]) -> None:
        short = parameters.get("shortWindow", 5)
        long = parameters.get("longWindow", 20)

        if not isinstance(short, int) or not isinstance(long, int):
            raise ValueError("shortWindow 和 longWindow 必须为整数")
        if short < 2:
            raise ValueError("shortWindow 不能小于 2")
        if long < 3:
            raise ValueError("longWindow 不能小于 3")
        if short >= long:
            raise ValueError("shortWindow 必须小于 longWindow")

    def generate_signals(
        self,
        prices: pd.DataFrame,
        parameters: Mapping[str, object],
    ) -> pd.Series:
        """基于收盘价计算信号。每行仅使用该行及之前的数据。"""
        self.validate_parameters(parameters)
        short_window = int(parameters.get("shortWindow", 5))
        long_window = int(parameters.get("longWindow", 20))

        if prices.empty or "close" not in prices.columns:
            return pd.Series(dtype=float)

        close = prices["close"].astype(float)

        short_ma = close.rolling(window=short_window, min_periods=short_window).mean()
        long_ma = close.rolling(window=long_window, min_periods=long_window).mean()

        # 信号：1 = 买入, -1 = 卖出, 0 = 持有
        signal = pd.Series(0, index=prices.index, dtype=float)

        # 金叉：短均线上穿长均线
        cross_above = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
        signal[cross_above] = 1.0

        # 死叉：短均线下穿长均线
        cross_below = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))
        signal[cross_below] = -1.0

        return signal
