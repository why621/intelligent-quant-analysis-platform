from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from quant_platform.interfaces import MarketDataProvider, Strategy
from quant_platform.models import (
    BacktestMetrics,
    BacktestRequest,
    BacktestResult,
    Trade,
)


class BacktestEngine:
    """异步回测引擎。

    MarketDataProvider 和一个 strategy 注册表通过构造函数注入。
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        strategies: Mapping[str, Strategy],
    ) -> None:
        self._provider = provider
        self._strategies = strategies

    def run(self, request: BacktestRequest) -> BacktestResult:
        self._validate(request)

        strategy = self._strategies[request.strategy_id]
        cash_per_symbol = request.initial_capital_cny / len(request.symbols)

        all_trades: list[Trade] = []
        equity_curves: dict[str, pd.Series] = {}

        for sym in request.symbols:
            prices = self._provider.history(
                sym, request.start_date, request.end_date, request.adjust
            )
            if prices.empty:
                continue
            signals = strategy.generate_signals(prices, request.parameters)
            trades, equity = self._simulate(
                sym, prices, signals, cash_per_symbol, request.trading_costs
            )
            all_trades.extend(trades)
            equity_curves[sym] = equity

        portfolio_equity = self._merge_equity(equity_curves)
        benchmark_equity = self._benchmark_curve(request, portfolio_equity.index)

        # 对齐净值曲线
        dates = portfolio_equity.index
        eq = pd.Series(portfolio_equity.values, index=dates, dtype=float)
        if benchmark_equity is not None:
            bm_vals = benchmark_equity.reindex(dates).values
        else:
            bm_vals = None
        bm = pd.Series(bm_vals, index=dates, dtype=float)

        metrics = _compute_metrics(eq, bm, request.initial_capital_cny)

        equity_df = pd.DataFrame({"date": dates, "equity": eq.values})
        equity_df["benchmarkEquity"] = bm.values if benchmark_equity is not None else None

        return BacktestResult(
            metrics=metrics,
            equity_curve=equity_df,
            trades=tuple(all_trades),
            assumptions={
                "signalAt": "close",
                "executeAt": "next_open",
                "calendar": "CN",
                "currency": "CNY",
            },
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _validate(self, request: BacktestRequest) -> None:
        if request.strategy_id not in self._strategies:
            raise ValueError(f"未知策略: {request.strategy_id}")
        if request.start_date >= request.end_date:
            raise ValueError("start_date 必须早于 end_date")
        if request.initial_capital_cny <= 0:
            raise ValueError("initial_capital_cny 必须大于 0")

    def _simulate(
        self,
        symbol: str,
        prices: pd.DataFrame,
        signals: pd.Series,
        capital: float,
        costs: object,
    ) -> tuple[list[Trade], pd.Series]:
        from quant_platform.models import TradingCosts

        if isinstance(costs, TradingCosts):
            commission = costs.commission_pct / 100
            stamp = costs.stamp_duty_pct / 100
            slippage = costs.slippage_pct / 100
        else:
            commission = stamp = slippage = 0.0

        prices = prices.set_index("date").sort_index()
        signals = signals.reindex(prices.index).fillna(0)

        cash = capital
        shares = 0.0
        trades: list[Trade] = []
        eq_values: dict[pd.Timestamp, float] = {}

        for i in range(len(prices) - 1):
            current_date = prices.index[i]  # type: ignore[assignment]
            signal = float(signals.iloc[i])
            next_open = float(prices["open"].iloc[i + 1])

            exec_price = next_open * (1 + slippage * (1 if signal >= 0 else -1))

            if signal == 1.0 and cash > 0:
                fee = cash * commission
                invest = cash - fee
                shares = invest / exec_price
                cash = 0.0
                trades.append(Trade(
                    trade_date=current_date,  # type: ignore[arg-type]
                    symbol=symbol,
                    side="buy",
                    price=exec_price,
                    quantity=shares,
                    amount_cny=invest,
                    fee_cny=fee,
                ))

            elif signal == -1.0 and shares > 0:
                gross = shares * exec_price
                fee = gross * (commission + stamp)
                cash = gross - fee
                trades.append(Trade(
                    trade_date=current_date,  # type: ignore[arg-type]
                    symbol=symbol,
                    side="sell",
                    price=exec_price,
                    quantity=shares,
                    amount_cny=gross,
                    fee_cny=fee,
                ))
                shares = 0.0

            close_price = float(prices["close"].iloc[i + 1])
            eq_values[prices.index[i + 1]] = cash + shares * close_price  # type: ignore[assignment]

        # 首日净值 = 初始资金
        eq_values[prices.index[0]] = capital  # type: ignore[assignment]

        return trades, pd.Series(eq_values).sort_index()

    def _merge_equity(self, curves: dict[str, pd.Series]) -> pd.Series:
        if not curves:
            return pd.Series(dtype=float)
        combined = pd.DataFrame(curves).ffill().sum(axis=1)
        return combined

    def _benchmark_curve(
        self,
        request: BacktestRequest,
        portfolio_dates: pd.DatetimeIndex,
    ) -> pd.Series | None:
        if request.benchmark is None:
            return None
        prices = self._provider.history(
            request.benchmark,
            request.start_date,
            request.end_date,
            request.adjust,
        )
        if prices.empty:
            return None
        prices = prices.set_index("date").sort_index()
        prices = prices.reindex(portfolio_dates).ffill()
        initial = float(prices["close"].iloc[0])
        return prices["close"] / initial


def _compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series | None,
    initial_capital: float,
) -> BacktestMetrics:
    if equity.empty:
        return BacktestMetrics(
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe=0.0,
            alpha_pct=None,
            beta=None,
        )
    total_return = (equity.iloc[-1] / initial_capital - 1) * 100

    # 年化收益率
    days = (equity.index[-1] - equity.index[0]).days  # type: ignore[operator]
    years = max(days / 365.25, 1 / 365.25)
    annualized = ((equity.iloc[-1] / initial_capital) ** (1 / years) - 1) * 100

    # 最大回撤（非负）
    peak = equity.expanding().max()
    drawdown = (1 - equity / peak) * 100
    max_dd = float(drawdown.max())

    # Sharpe
    daily_ret = equity.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std() * math.sqrt(252))
    else:
        sharpe = 0.0

    # Alpha / Beta
    alpha: float | None = None
    beta: float | None = None
    if benchmark is not None and not benchmark.dropna().empty and len(daily_ret) > 1:
        bm_ret = benchmark.pct_change().dropna()
        common = daily_ret.index.intersection(bm_ret.index)
        if len(common) > 1:
            dr = daily_ret[common]
            br = bm_ret[common]
            cov = np.cov(dr, br)
            if cov[0, 1] != 0 and cov[1, 1] > 0:
                beta = float(cov[0, 1] / cov[1, 1])
                alpha = float(dr.mean() - (beta * br.mean())) * 252 * 100
            else:
                alpha = None
                beta = None

    return BacktestMetrics(
        total_return_pct=total_return,
        annualized_return_pct=annualized,
        max_drawdown_pct=max_dd,
        sharpe=sharpe,
        alpha_pct=alpha,
        beta=beta,
    )
