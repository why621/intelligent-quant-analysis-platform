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
        if request.portfolio_mode == "shared_account":
            return self._run_shared(request)

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
        account_curves = {}

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
            points = []
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
                account_points=points,
                asset_type=self._asset_types(request.symbols).get(sym, "stock"),
            )
            account_curves[sym] = points
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
                "portfolioMode": "legacy_independent",
                "benchmarkReturnBasis": "price_index"
                if request.benchmark == "index:CSI:000300"
                else "adjusted_etf"
                if request.benchmark
                else "none",
            },
            account_curve=self._combine_accounts(account_curves, dates),
            cost_summary=self._cost_summary(all_trades),
            benchmark_context=self._benchmark_context(request, dates),
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _stamp(costs, asset_type, day, fallback=0.0):
        if getattr(costs, "stamp_duty_mode", "fixed") == "fixed":
            return fallback
        from quant_platform.portfolio.execution import stamp_duty_rate
        return stamp_duty_rate(asset_type, pd.Timestamp(day).date(), costs)

    def _asset_types(self, symbols):
        listing = getattr(self._provider, "list_assets", None)
        if listing is None:
            return {}
        return {a.symbol: a.asset_type for a in listing(query=None, asset_type=None, limit=None)}

    @staticmethod
    def _point(day, cash, quantities, prices, symbols, fees, slippage):
        values = np.asarray(quantities) * np.asarray(prices)
        equity = float(cash + values.sum())
        return {"date": pd.Timestamp(day).date().isoformat(), "cashCny": float(cash),
                "equity": equity,
                "exposurePct": float(values.sum() / equity * 100) if equity > 0 else 0.0,
                "positions": [{"symbol": s, "quantity": float(q), "marketValueCny": float(v),
                               "weightPct": float(v / equity * 100) if equity > 0 else 0.0}
                              for s, q, v in zip(symbols, quantities, values, strict=True)],
                "cumulativeFeesCny": float(fees), "cumulativeSlippageCny": float(slippage),
                "cumulativeTradingCostCny": float(fees + slippage)}

    @staticmethod
    def _cost_summary(trades):
        commission = sum(t.commission_cny or 0 for t in trades)
        stamp = sum(t.stamp_duty_cny or 0 for t in trades)
        fees = sum(t.fee_cny for t in trades)
        slip = sum(t.slippage_cny or 0 for t in trades)
        return {"tradeCount": len(trades), "commissionCny": commission,
                "stampDutyCny": stamp, "feesCny": fees, "slippageCny": slip,
                "totalTradingCostCny": fees + slip}

    def _benchmark_context(self, request, dates):
        mode = request.benchmark_mode or ("custom" if request.benchmark else "none")
        return {"mode": mode, "symbols": list(request.symbols) if mode == "buy_and_hold"
                else [request.benchmark] if mode == "custom" else [],
                "startDate": pd.Timestamp(dates[0]).date().isoformat() if len(dates) else None,
                "endDate": pd.Timestamp(dates[-1]).date().isoformat() if len(dates) else None,
                "returnBasis": ("initial_equal_weight_price_hold" if mode == "buy_and_hold"
                                else "price_index" if request.benchmark == "index:CSI:000300"
                                else "adjusted_price" if mode == "custom" else "none"),
                "costsIncluded": False,
                "label": ("标的买入持有（初始等权、不再平衡、不计交易费用）"
                          if mode == "buy_and_hold" else "自定义价格基准（不计交易费用）"
                          if mode == "custom" else "无比较基准")}

    def _combine_accounts(self, curves, dates):
        if not curves:
            return ()
        lookup = {s: {p["date"]: p for p in points} for s, points in curves.items()}
        last = {}
        combined = []
        for day in dates:
            key = pd.Timestamp(day).date().isoformat()
            for s, points in lookup.items():
                if key in points:
                    last[s] = points[key]
            if len(last) != len(curves):
                continue
            equity = sum(p["equity"] for p in last.values())
            cash = sum(p["cashCny"] for p in last.values())
            positions = [dict(pos, weightPct=pos["marketValueCny"] / equity * 100)
                         for p in last.values() for pos in p["positions"]]
            fees = sum(p["cumulativeFeesCny"] for p in last.values())
            slip = sum(p["cumulativeSlippageCny"] for p in last.values())
            combined.append({"date": key, "cashCny": cash, "equity": equity,
                             "exposurePct": (equity - cash) / equity * 100,
                             "positions": positions, "cumulativeFeesCny": fees,
                             "cumulativeSlippageCny": slip,
                             "cumulativeTradingCostCny": fees + slip})
        return tuple(combined)

    def _run_shared(self, request):
        from quant_platform.portfolio.execution import (
            PORTFOLIO_EXECUTION_VERSION,
            rebalance_portfolio,
            signal_target_weights,
        )

        strategy = self._resolve_strategy(request)
        info = strategy.info()
        if info.requires_trained_model or info.signal_semantics != "discrete_hold":
            raise ValueError("旧单资产模型不支持共享组合；请使用独立组合模型环境")
        frames, signals = {}, {}
        for symbol in request.symbols:
            frame = self._provider.history(symbol, request.start_date, request.end_date,
                                           request.adjust).copy()
            if frame.empty or len(frame) < 2:
                raise ValueError(f"{symbol}: 共享组合至少需要两根有效行情")
            dates = pd.to_datetime(frame["date"])
            if dates.duplicated().any() or not dates.is_monotonic_increasing:
                raise ValueError(f"{symbol}: 行情日期重复或未排序")
            values = frame[["open", "close"]].to_numpy(dtype=float)
            if not np.isfinite(values).all() or (values <= 0).any():
                raise ValueError(f"{symbol}: 非法成交或估值价格")
            generated = strategy.generate_signals(frame, request.parameters)
            if len(generated) != len(frame):
                raise ValueError("strategy signals must have one value per price row")
            frame.index = pd.DatetimeIndex(dates)
            frames[symbol] = frame
            signals[symbol] = pd.Series(generated.to_numpy(), index=frame.index)
        from quant_platform.data.calendar import sessions

        observed_dates = pd.DatetimeIndex(sorted(set().union(
            *(set(f.index) for f in frames.values()))))
        # A session remains on the account clock even when ALL assets are suspended.
        # Otherwise a day-only order would accidentally survive until reopening.
        dates = pd.DatetimeIndex(pd.to_datetime(sessions(
            observed_dates[0].date(), request.end_date)))
        if not observed_dates.difference(dates).empty:
            raise ValueError("共享组合行情包含非官方交易日")
        nontrading = getattr(self._provider, "nontrading_sessions", None)
        for symbol, frame in frames.items():
            allowed = (set(pd.to_datetime(list(nontrading(
                symbol, request.start_date, request.end_date)))) if callable(nontrading) else set())
            if dates[0] not in frame.index or any(
                day not in allowed for day in dates.difference(frame.index)
            ):
                raise ValueError(f"{symbol}: 共享组合日期缺口未经核实")
        asset_types = self._asset_types(request.symbols)
        if request.trading_costs.stamp_duty_mode == "asset_date" and any(
            s not in asset_types for s in request.symbols
        ):
            raise ValueError("自动税率需要明确资产类型")
        cash = request.initial_capital_cny
        quantities = np.zeros(len(request.symbols), dtype=float)
        last_close = np.array(
            [frames[s].loc[dates[0], "close"] for s in request.symbols], dtype=float)
        points = [self._point(dates[0], cash, quantities, last_close, request.symbols, 0, 0)]
        trades = []
        fees = slip = 0.0
        for day, following in zip(dates[:-1], dates[1:], strict=True):
            equity = cash + np.dot(quantities, last_close)
            weights = quantities * last_close / equity
            decisions = np.array([signals[s].get(day, 0.0) for s in request.symbols], dtype=float)
            if not np.isfinite(decisions).all() or not np.isin(decisions, [-1, 0, 1]).all():
                raise ValueError("传统组合信号必须是-1/0/1")
            tradable = [following in frames[s].index for s in request.symbols]
            opens = np.array([
                frames[s].loc[following, "open"] if ok else last_close[k]
                for k, (s, ok) in enumerate(zip(request.symbols, tradable, strict=True))])
            if np.any(decisions != 0):
                target = signal_target_weights(decisions, weights, cash_pct=request.cash_pct)
                result = rebalance_portfolio(
                    cash=cash, quantities=quantities, target_weights=target,
                    prices=opens, symbols=request.symbols,
                    asset_types=[asset_types.get(s, "stock") for s in request.symbols],
                    trade_date=following.date(), costs=request.trading_costs, tradable=tradable)
                cash, quantities = result.cash, result.quantities
                for fill in result.fills:
                    fees += fill.fee_cny
                    slip += fill.slippage_cny
                    trades.append(Trade(following.date(), fill.symbol, fill.side, fill.price,
                        fill.quantity, fill.amount_cny, fill.fee_cny, fill.commission_cny,
                        fill.stamp_duty_cny, fill.slippage_cny))
            last_close = np.array([
                frames[s].loc[following, "close"] if ok else last_close[k]
                for k, (s, ok) in enumerate(zip(request.symbols, tradable, strict=True))])
            points.append(self._point(following, cash, quantities, last_close,
                                      request.symbols, fees, slip))
        eq = pd.Series([p["equity"] for p in points], index=dates, dtype=float)
        benchmark = self._benchmark_curve(request, dates)
        curve = pd.DataFrame({"date": dates, "equity": eq.values,
                             "benchmarkEquity": None if benchmark is None else benchmark.values})
        return BacktestResult(_compute_metrics(eq, benchmark, request.initial_capital_cny), curve,
            tuple(trades), {"signalAt": "close", "executeAt": "next_open", "calendar": "CN",
                "currency": "CNY", "portfolioMode": "shared_account",
                "signalSemantics": "discrete_hold",
                "executionVersion": PORTFOLIO_EXECUTION_VERSION,
                "costBasis": request.trading_costs.stamp_duty_mode,
                "nonTradingExecution": "skip_untradable_no_pending_order",
                "nonTradingValuation": "last_observed_close_or_initial_cash"
                if any(len(f) != len(dates) for f in frames.values()) else "none"},
            tuple(points), self._cost_summary(trades), self._benchmark_context(request, dates))

    def _validate(self, request: BacktestRequest) -> None:
        if request.strategy_id not in self._strategies:
            raise ValueError(f"未知策略: {request.strategy_id}")
        if request.start_date >= request.end_date:
            raise ValueError("start_date 必须早于 end_date")
        if not math.isfinite(request.initial_capital_cny) or request.initial_capital_cny <= 0:
            raise ValueError("initial_capital_cny 必须大于 0")
        if not 1 <= len(request.symbols) <= 10 or len(set(request.symbols)) != len(request.symbols):
            raise ValueError("symbols 必须包含1至10个不重复资产")
        if request.portfolio_mode not in {"shared_account", "legacy_independent"}:
            raise ValueError("未知组合执行模式")
        if not math.isfinite(request.cash_pct) or not 0 <= request.cash_pct <= 100:
            raise ValueError("cash_pct 必须在0至100之间")
        if request.portfolio_mode == "legacy_independent" and request.cash_pct:
            raise ValueError("现金预留仅适用于共享账户")
        if request.benchmark_mode not in {None, "buy_and_hold", "custom", "none"}:
            raise ValueError("未知基准模式")
        if request.benchmark_mode == "custom" and not request.benchmark:
            raise ValueError("自定义基准需要明确资产")
        costs = request.trading_costs
        if costs.stamp_duty_mode not in {"fixed", "asset_date"}:
            raise ValueError("未知费用模式")
        if any(not math.isfinite(v) or not 0 <= v < 100 for v in (
            costs.commission_pct, costs.stamp_duty_pct, costs.slippage_pct
        )):
            raise ValueError("费率必须是0至100之间有限数值")
        if costs.stamp_duty_mode == "asset_date":
            known = self._asset_types(request.symbols)
            if any(known.get(s) not in {"stock", "etf"} for s in request.symbols):
                raise ValueError("自动税率需要明确资产类型")

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
        account_points=None,
        asset_type="stock",
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
        prices["date"] = pd.to_datetime(prices["date"])
        prices = prices.set_index("date").sort_index()
        cash, shares = capital, 0.0
        trades: list[Trade] = []
        eq_values = {prices.index[0]: capital}
        previous_target = 0.0
        fees = slippage_total = 0.0
        if account_points is not None:
            account_points.append(self._point(prices.index[0], cash, [shares],
                                             [float(prices["close"].iloc[0])], [symbol], 0, 0))
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
                semantics=semantics, commission=commission,
                stamp=self._stamp(costs, asset_type, prices.index[i + 1], stamp),
                slippage=slippage, band_pct=band_pct, min_trade_cny=min_trade_cny,
            )
            if fill is not None:
                stamp_paid = (fill.amount * self._stamp(costs, asset_type,
                              prices.index[i + 1], stamp) if fill.side == "sell" else 0.0)
                slip_paid = abs(fill.price - float(prices["open"].iloc[i + 1])) * fill.quantity
                fees += fill.fee
                slippage_total += slip_paid
                trades.append(Trade(
                    trade_date=pd.Timestamp(prices.index[i + 1]).date(),
                    symbol=symbol, side=fill.side, price=fill.price,
                    quantity=fill.quantity, amount_cny=fill.amount, fee_cny=fill.fee,
                    commission_cny=fill.fee - stamp_paid, stamp_duty_cny=stamp_paid,
                    slippage_cny=slip_paid,
                ))
            eq_values[prices.index[i + 1]] = cash + shares * float(prices["close"].iloc[i + 1])
            if account_points is not None:
                account_points.append(self._point(prices.index[i + 1], cash, [shares],
                    [float(prices["close"].iloc[i + 1])], [symbol], fees, slippage_total))
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
        mode = request.benchmark_mode or ("custom" if request.benchmark else "none")
        if mode == "none":
            return None
        if mode == "buy_and_hold":
            normalized = []
            for symbol in request.symbols:
                frame = self._provider.history(symbol, request.start_date, request.end_date,
                                               request.adjust).copy()
                frame["date"] = pd.to_datetime(frame["date"])
                close = (frame.set_index("date")["close"].sort_index()
                         .reindex(portfolio_dates).ffill())
                if close.empty or close.isna().any() or (close <= 0).any():
                    raise ValueError("买入持有基准缺少有效价格")
                normalized.append(close / float(close.iloc[0]))
            return pd.concat(normalized, axis=1).mean(axis=1)
        prices = self._provider.history(
            request.benchmark,
            request.start_date,
            request.end_date,
            request.adjust,
        )
        if prices.empty:
            return None
        prices = prices.copy()
        prices["date"] = pd.to_datetime(prices["date"])
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
