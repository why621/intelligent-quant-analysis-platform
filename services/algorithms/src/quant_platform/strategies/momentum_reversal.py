from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from quant_platform.models import StrategyInfo


class MomentumReversalStrategy:
    """动量反转策略：近期收益超过阈值视为超买（卖出），低于负阈值视为超卖（买入）。"""

    id: str = "momentum_reversal"

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self.id,
            name="动量反转",
            category="traditional",
            status="available",
            description=(
                "计算回顾期内的累计收益率，超过上阈值视为超买（卖出信号），"
                "低于下阈值视为超卖（买入信号）。收盘生成信号，下一交易日开盘成交。"
            ),
            parameter_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["lookback", "overboughtThreshold", "oversoldThreshold"],
                "properties": {
                    "lookback": {
                        "type": "integer",
                        "minimum": 3,
                        "default": 10,
                        "description": "回顾窗口（交易日数）",
                    },
                    "overboughtThreshold": {
                        "type": "number",
                        "default": 5.0,
                        "description": "超买阈值（百分点），累计收益高于此值→卖出",
                    },
                    "oversoldThreshold": {
                        "type": "number",
                        "default": -5.0,
                        "description": "超卖阈值（百分点），累计收益低于此值→买入",
                    },
                },
            },
        )

    def validate_parameters(self, parameters: Mapping[str, object]) -> None:
        lookback = parameters.get("lookback", 10)
        overbought = parameters.get("overboughtThreshold", 5.0)
        oversold = parameters.get("oversoldThreshold", -5.0)

        if not isinstance(lookback, int):
            raise ValueError("lookback 必须为整数")
        if lookback < 3:
            raise ValueError("lookback 不能小于 3")
        if not isinstance(overbought, (int, float)):
            raise ValueError("overboughtThreshold 必须为数值")
        if not isinstance(oversold, (int, float)):
            raise ValueError("oversoldThreshold 必须为数值")
        if overbought <= oversold:
            raise ValueError("overboughtThreshold 必须大于 oversoldThreshold")

    def generate_signals(
        self,
        prices: pd.DataFrame,
        parameters: Mapping[str, object],
    ) -> pd.Series:
        self.validate_parameters(parameters)
        lookback = int(parameters.get("lookback", 10))
        overbought = float(parameters.get("overboughtThreshold", 5.0))
        oversold = float(parameters.get("oversoldThreshold", -5.0))

        if prices.empty or "close" not in prices.columns:
            return pd.Series(dtype=float)

        close = prices["close"].astype(float)

        # 回顾期内累计收益率（百分点）
        momentum = close.pct_change(periods=lookback) * 100

        signal = pd.Series(0, index=prices.index, dtype=float)
        signal[momentum > overbought] = -1.0  # 超买 → 卖出
        signal[momentum < oversold] = 1.0  # 超卖 → 买入

        return signal
