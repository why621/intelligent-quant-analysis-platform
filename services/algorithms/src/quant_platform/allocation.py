from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from quant_platform.interfaces import MarketDataProvider, Strategy
from quant_platform.models import (
    AllocationAction,
    AllocationPosition,
    AllocationSuggestion,
)


class AllocationService:
    """下一交易日模拟配置建议。

    基于各资产最近信号生成权重，仅用于研究，不提交真实订单。
    """

    _LOOKBACK_DAYS = 365

    def __init__(
        self,
        provider: MarketDataProvider,
        strategies: dict[str, Strategy],
    ) -> None:
        self._provider = provider
        self._strategies = strategies

    def suggest(
        self,
        *,
        symbols: Sequence[str],
        strategy_id: str,
        cash_pct: float = 0,
    ) -> AllocationSuggestion:
        if strategy_id not in self._strategies:
            raise ValueError(f"未知策略: {strategy_id}")

        strategy = self._strategies[strategy_id]
        today = date.today()
        lookback_start = today - timedelta(days=self._LOOKBACK_DAYS)

        signals: dict[str, float] = {}
        for sym in symbols:
            prices = self._provider.history(sym, lookback_start, today)
            if prices.empty or len(prices) < 10:
                signals[sym] = 0.0
                continue
            sig = strategy.generate_signals(prices, {})
            signals[sym] = float(sig.iloc[-1]) if len(sig) > 0 else 0.0

        # 买入/持有信号的资产等权分配
        buy_symbols = [s for s, v in signals.items() if v == 1.0]
        hold_symbols = [s for s, v in signals.items() if v == 0.0]

        investable_count = len(buy_symbols) + len(hold_symbols)
        weight_per = (100.0 - cash_pct) / max(investable_count, 1)

        positions: list[AllocationPosition] = []

        for sym in symbols:
            sig = signals.get(sym, 0.0)
            action, reason = _signal_to_action(sig)

            if sig == -1.0:
                w = 0.0
            elif sig == 1.0:
                w = weight_per
            elif investable_count == 0:
                w = 0.0
            else:
                w = weight_per

            positions.append(AllocationPosition(
                symbol=sym,
                weight_pct=w,
                action=action,
                reason=reason,
            ))

        basis = today - timedelta(days=1)
        target = _next_trading_day(basis)

        return AllocationSuggestion(
            basis_date=basis,
            target_date=target,
            strategy_id=strategy_id,
            positions=tuple(positions),
            cash_pct=cash_pct,
        )


def _signal_to_action(signal: float) -> tuple[AllocationAction, str]:
    if signal == 1.0:
        return "increase", "策略信号为买入"
    elif signal == -1.0:
        return "exit", "策略信号为卖出"
    return "hold", "策略信号中性"


def _next_trading_day(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d
