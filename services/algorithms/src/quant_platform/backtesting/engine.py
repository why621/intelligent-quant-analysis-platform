from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from quant_platform.backtesting.execution import execute_bar
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

        strategy = self._resolve_strategy(request)
        # Tolerate strategies that predate the info() metadata contract:
        # default to the historical discrete-hold behaviour when unavailable.
        info = strategy.info() if hasattr(strategy, "info") else None
        semantics = getattr(info, "signal_semantics", "discrete_hold")
        band_pct = float(getattr(strategy, "rebalance_band_pct", 0.005))
        min_trade_cny = float(getattr(strategy, "min_trade_cny", 100.0))
        cash_per_symbol = request.initial_capital_cny / len(request.symbols)

        uses_nontrading_valuation = False
        all_trades: list[Trade] = []
        equity_curves: dict[str, pd.Series] = {}

        for sym in request.symbols:
            prices = self._provider.history(
                sym, request.start_date, request.end_date, request.adjust
            )
            if prices.empty and not callable(getattr(strategy, "prepare_inference", None)):
                continue
            prepare = getattr(strategy, "prepare_inference", None)
            signal_at = prepare(prices, request.parameters) if callable(prepare) else None
            signals = (
                pd.Series(float("nan"), index=prices.index)
                if signal_at is not None
                else strategy.generate_signals(prices, request.parameters)
            )
            trades, equity = self._simulate(
                sym,
                prices,
                signals,
                cash_per_symbol,
                request.trading_costs,
                semantics,
                band_pct,
                min_trade_cny,
                signal_at=signal_at,
            )
            all_trades.extend(trades)
            nontrading = getattr(self._provider, "nontrading_sessions", None)
            if nontrading and nontrading(sym, request.start_date, request.end_date):
                from quant_platform.data.calendar import sessions

                # Extend VALUE only. No synthetic OHLCV or fills on suspended days.
                grid = pd.to_datetime(sessions(request.start_date, request.end_date))
                equity = equity.reindex(grid).ffill().fillna(cash_per_symbol)
                uses_nontrading_valuation = True
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
                "executeAt": "next_tradable_open" if uses_nontrading_valuation else "next_open",
                "nonTradingValuation": "last_observed_close_or_initial_cash"
                if uses_nontrading_valuation
                else "none",
                "signalSemantics": semantics,
                "rebalanceBandPct": (
                    str(band_pct) if semantics == "continuous_target_weight" else "n/a"
                ),
                "calendar": "CN",
                "currency": "CNY",
                "benchmarkReturnBasis": "price_index"
                if request.benchmark == "index:CSI:000300"
                else "adjusted_etf"
                if request.benchmark
                else "none",
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

    def _resolve_strategy(self, request: BacktestRequest) -> Strategy:
        """Return the strategy instance to run this request with.

        Strategies that expose ``create_for_request(parameters)`` (duck-typed,
        same convention as ``nontrading_sessions`` / ``cache_revision``) get a
        fresh per-request instance so trained model state never races across
        concurrent backtests. Everything else keeps the shared singleton.
        """
        strategy = self._strategies[request.strategy_id]
        factory = getattr(strategy, "create_for_request", None)
        if callable(factory):
            return factory(request.parameters)
        return strategy

    def _simulate(
        self,
        symbol: str,
        prices: pd.DataFrame,
        signals: pd.Series,
        capital: float,
        costs: object,
        semantics: str = "discrete_hold",
        band_pct: float = 0.005,
        min_trade_cny: float = 100.0,
        *,
        signal_at=None,
    ) -> tuple[list[Trade], pd.Series]:
        from quant_platform.models import TradingCosts

        if isinstance(costs, TradingCosts):
            commission = costs.commission_pct / 100
            stamp = costs.stamp_duty_pct / 100
            slippage = costs.slippage_pct / 100
        else:
            commission = stamp = slippage = 0.0
        if len(signals) != len(prices):
            raise ValueError("strategy signals must have one value per price row")
        prices = prices.copy()
        prices["_signal"] = signals.to_numpy(copy=False)
        prices = prices.set_index("date").sort_index()
        cash, shares = capital, 0.0
        trades: list[Trade] = []
        eq_values = {prices.index[0]: capital}
        previous_target = 0.0
        continuous = semantics == "continuous_target_weight"
        for i in range(len(prices) - 1):
            close = float(prices["close"].iloc[i])
            equity = cash + shares * close
            weight = shares * close / equity if equity > 0 else 0.0
            # RL observes the account that actually executed previous orders,
            # including request-specific costs, capital and rebalance thresholds.
            signal = float(signal_at(i, weight) if signal_at is not None
                           else prices["_signal"].iloc[i])
            if math.isnan(signal):
                signal = previous_target if continuous else 0.0
            if continuous:
                signal = min(1.0, max(0.0, signal))
                previous_target = signal
            cash, shares, fill = execute_bar(
                cash, shares, signal, close, float(prices["open"].iloc[i + 1]),
                semantics=semantics, commission=commission, stamp=stamp,
                slippage=slippage, band_pct=band_pct, min_trade_cny=min_trade_cny,
            )
            if fill is not None:
                trades.append(Trade(
                    trade_date=pd.Timestamp(prices.index[i + 1]).date(),
                    symbol=symbol, side=fill.side, price=fill.price,
                    quantity=fill.quantity, amount_cny=fill.amount, fee_cny=fill.fee,
                ))
            eq_values[prices.index[i + 1]] = cash + shares * float(prices["close"].iloc[i + 1])
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
            if cov[1, 1] > 0:
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
