from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from quant_platform.data.akshare_provider import UpstreamUnavailableError
from quant_platform.data.calendar import CalendarUnavailableError, is_session, latest_session
from quant_platform.interfaces import MarketDataProvider, Strategy
from quant_platform.models import (
    AllocationAction,
    AllocationPosition,
    AllocationSuggestion,
    BacktestRequest,
    TradingCosts,
)


class PublicationUnavailableError(UpstreamUnavailableError):
    pass


class StalePublicationError(UpstreamUnavailableError):
    def __init__(self, available, required):
        super().__init__("published allocation history is stale or ahead of the completed day")
        self.available = available
        self.required = required


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
        parameters: Mapping[str, object] | None = None,
        adjust: str = "qfq",
        trading_costs: TradingCosts | None = None,
        initial_capital_cny: float = 100000,
        start_date: date | None = None,
    ) -> AllocationSuggestion:
        if strategy_id not in self._strategies:
            raise ValueError(f"未知策略: {strategy_id}")

        strategy = self._strategies[strategy_id]
        info = strategy.info()
        resolved_parameters = (
            dict(parameters)
            if parameters is not None
            else {
                key: schema["default"]
                for key, schema in info.parameter_schema.get("properties", {}).items()
                if "default" in schema
            }
        )
        strategy.validate_parameters(resolved_parameters)
        costs = trading_costs or TradingCosts()
        # Allocation consumes discrete {-1,0,1} signals with empty parameters;
        # RL (trained-model) and continuous-target strategies cannot supply them.
        joint = getattr(strategy, "joint_portfolio", False)
        if not joint and (info.requires_trained_model or info.signal_semantics != "discrete_hold"):
            raise ValueError("配置建议仅支持离散持仓策略，强化学习/连续权重策略不适用")
        try:
            required = latest_session(_today() - timedelta(days=1))
            status = self._provider.status()
            basis = status.latest_trade_date
            state = status.components.get("history", {}).get("status", status.status)
            if basis is None or state in {"failed", "updating"}:
                raise PublicationUnavailableError("no usable history publication")
            if basis != required:
                raise StalePublicationError(basis, required)
            target = _next_trading_day(basis)
        except CalendarUnavailableError as exc:
            raise UpstreamUnavailableError(str(exc)) from exc
        lookback_start = start_date or basis - timedelta(days=self._LOOKBACK_DAYS)
        if lookback_start >= basis:
            raise ValueError("模拟重放起点必须早于依据日")

        if joint:
            from quant_platform.backtesting.engine import BacktestEngine

            engine = BacktestEngine(self._provider, self._strategies)
            request = BacktestRequest(
                symbols=tuple(symbols),
                strategy_id=strategy_id,
                parameters=resolved_parameters,
                start_date=lookback_start,
                end_date=basis,
                adjust=adjust,
                initial_capital_cny=initial_capital_cny,
                trading_costs=costs,
                portfolio_mode="shared_account",
                cash_pct=cash_pct,
            )
            engine._validate(request)
            replay, weights = strategy.run_joint(engine, request, with_target=True)
            current = {p["symbol"]: p["weightPct"] for p in replay.account_curve[-1]["positions"]}
            positions = tuple(
                AllocationPosition(
                    s,
                    float(weights[s] * 100),
                    "increase"
                    if weights[s] * 100 > current[s] + 1e-8
                    else "decrease"
                    if weights[s] * 100 < current[s] - 1e-8
                    else "hold",
                    "组合模型联合目标；按同参数共享账户重放，下一开盘实际成交与费用未知",
                )
                for s in symbols
            )
            return AllocationSuggestion(
                basis_date=basis,
                target_date=target,
                strategy_id=strategy_id,
                positions=positions,
                cash_pct=max(0.0, 100 - sum(weights.values()) * 100),
                request={
                    "symbols": list(symbols),
                    "strategyId": strategy_id,
                    "cashPct": cash_pct,
                    "parameters": resolved_parameters,
                    "adjust": adjust,
                    "initialCapitalCny": initial_capital_cny,
                    "startDate": lookback_start.isoformat(),
                    "tradingCosts": strategy.bundle.manifest["tradingCosts"],
                },
            )

        signals: dict[str, float] = {}
        for sym in symbols:
            prices = self._provider.history(sym, lookback_start, basis, adjust)
            if prices.empty or len(prices) < 10:
                raise UpstreamUnavailableError(f"{sym}: insufficient allocation history")
            dates = pd.to_datetime(prices["date"], errors="coerce")
            if (
                dates.isna().any()
                or dates.duplicated().any()
                or not dates.is_monotonic_increasing
                or dates.iloc[-1].date() != basis
            ):
                raise UpstreamUnavailableError(f"{sym}: allocation history is stale or invalid")
            sig = strategy.generate_signals(prices, resolved_parameters)
            if len(sig) != len(prices) or not sig.index.equals(prices.index):
                raise UpstreamUnavailableError(f"{sym}: missing or misaligned allocation signal")
            value = float(sig.iloc[-1])
            if value not in (-1.0, 0.0, 1.0):
                raise UpstreamUnavailableError(f"{sym}: invalid allocation signal")
            signals[sym] = value

        from quant_platform.backtesting.engine import BacktestEngine
        from quant_platform.portfolio.execution import signal_target_weights

        replay = BacktestEngine(self._provider, self._strategies).run(
            BacktestRequest(
                symbols=tuple(symbols),
                strategy_id=strategy_id,
                parameters=resolved_parameters,
                start_date=lookback_start,
                end_date=basis,
                adjust=adjust,
                initial_capital_cny=initial_capital_cny,
                trading_costs=costs,
                portfolio_mode="shared_account",
                cash_pct=cash_pct,
            )
        )
        last = replay.account_curve[-1]
        current = [p["weightPct"] / 100 for p in last["positions"]]
        targets = signal_target_weights([signals[s] for s in symbols], current, cash_pct=cash_pct)

        positions: list[AllocationPosition] = []

        for index, sym in enumerate(symbols):
            sig = signals.get(sym, 0.0)
            action, reason = _signal_to_action(sig)

            w = float(targets[index]) * 100
            if sig != -1:
                difference = w - current[index] * 100
                action = (
                    "increase"
                    if difference > 1e-8
                    else "decrease"
                    if difference < -1e-8
                    else "hold"
                )
            if sig == 0:
                reason = "无新交易信号；沿用历史重放账户，空仓不因中性信号建仓"

            positions.append(
                AllocationPosition(
                    symbol=sym,
                    weight_pct=w,
                    action=action,
                    reason=reason,
                )
            )

        return AllocationSuggestion(
            basis_date=basis,
            target_date=target,
            strategy_id=strategy_id,
            positions=tuple(positions),
            cash_pct=max(0.0, 100.0 - float(sum(targets)) * 100),
            request={
                "symbols": list(symbols),
                "strategyId": strategy_id,
                "cashPct": cash_pct,
                "parameters": resolved_parameters,
                "adjust": adjust,
                "initialCapitalCny": initial_capital_cny,
                "startDate": lookback_start.isoformat(),
                "tradingCosts": {
                    "commissionPct": costs.commission_pct,
                    "stampDutyPct": costs.stamp_duty_pct,
                    "slippagePct": costs.slippage_pct,
                    "stampDutyMode": costs.stamp_duty_mode,
                },
            },
        )


def _signal_to_action(signal: float) -> tuple[AllocationAction, str]:
    if signal == 1.0:
        return "increase", "策略信号为买入"
    elif signal == -1.0:
        return "exit", "策略信号为卖出"
    return "hold", "策略信号中性"


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _next_trading_day(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_session(d):
        d = d + timedelta(days=1)
    return d
