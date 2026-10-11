"""One cash ledger for portfolio backtests, forecasts and training.

The caller decides using information through close t, then supplies open t+1
prices here. Slippage is inside the fill price; it is reported, never debited
a second time. No ML dependencies, independent asset accounts or borrowing.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from quant_platform.models import TradingCosts

PORTFOLIO_EXECUTION_VERSION = "shared-portfolio-v1"
_EPS = 1e-10


@dataclass(frozen=True)
class PortfolioFill:
    symbol: str
    index: int
    side: str
    price: float
    quantity: float
    amount_cny: float
    commission_cny: float
    stamp_duty_cny: float
    slippage_cny: float

    @property
    def fee_cny(self) -> float:
        return self.commission_cny + self.stamp_duty_cny

    @property
    def total_cost_cny(self) -> float:
        return self.fee_cny + self.slippage_cny


@dataclass(frozen=True)
class PortfolioExecution:
    cash: float
    quantities: np.ndarray
    fills: tuple[PortfolioFill, ...]


def _rate(value: float, name: str) -> float:
    if not math.isfinite(value) or not 0 <= value < 100:
        raise ValueError(f"{name} must be finite and in [0, 100)")
    return float(value) / 100.0


def stamp_duty_rate(asset_type: str, trade_date: date, costs: TradingCosts) -> float:
    """Sell-only rate. Fixed mode retains the explicit historical experiment.

    Asset/date mode covers the supported post-2008 A-share research period.
    Sources and dates are recorded in the CR065 research/design documentation.
    """
    if asset_type not in {"stock", "etf"}:
        raise ValueError("asset_type must be stock or etf")
    mode = getattr(costs, "stamp_duty_mode", "fixed")
    if mode == "fixed":
        return _rate(costs.stamp_duty_pct, "stamp_duty_pct")
    if mode != "asset_date":
        raise ValueError("stamp_duty_mode must be fixed or asset_date")
    if asset_type == "etf":
        return 0.0
    if trade_date < date(2008, 9, 19):
        raise ValueError("asset_date stock tax history starts on 2008-09-19")
    return 0.001 if trade_date < date(2023, 8, 28) else 0.0005


def signal_target_weights(
    signals: Sequence[float], current_weights: Sequence[float], *, cash_pct: float = 0.0
) -> np.ndarray:
    """Shared rule baseline: hold never creates a position from cash.

    On an actual buy/sell event, distribute the investable budget equally over
    positions to retain and assets to buy. With no event, retain actual weights
    (including drift), rather than charging for an unintended daily rebalance.
    This rule baseline is not a learned portfolio optimiser.
    """
    signal = np.asarray(signals, dtype=float)
    current = np.asarray(current_weights, dtype=float)
    if signal.ndim != 1 or signal.shape != current.shape or not 1 <= len(signal) <= 10:
        raise ValueError("signals and weights must have matching 1..10 asset slots")
    if not np.isfinite(signal).all() or not np.isin(signal, [-1.0, 0.0, 1.0]).all():
        raise ValueError("signals must be finite sell/hold/buy values -1/0/1")
    if not np.isfinite(current).all() or (current < 0).any() or current.sum() > 1 + _EPS:
        raise ValueError("current weights must be nonnegative with sum <= 1")
    if not math.isfinite(cash_pct) or not 0 <= cash_pct <= 100:
        raise ValueError("cash_pct must be finite and in [0, 100]")
    if not np.any(signal):
        return current.copy()
    active = (signal > 0) | ((signal == 0) & (current > _EPS))
    result = np.zeros_like(current)
    if active.any():
        result[active] = (1 - cash_pct / 100.0) / int(active.sum())
    return result


def rebalance_portfolio(
    *,
    cash: float,
    quantities: Sequence[float],
    target_weights: Sequence[float],
    prices: Sequence[float],
    symbols: Sequence[str],
    asset_types: Sequence[str],
    trade_date: date,
    costs: TradingCosts,
    tradable: Sequence[bool] | None = None,
    band_pct: float = 0.0,
    min_trade_cny: float = 0.0,
) -> PortfolioExecution:
    """Execute a joint target; target excludes the residual cash slot.

    Targets are sized against pre-trade open NAV. Sales occur first; all buy
    orders then share one proportional affordability factor, so symbol order
    cannot determine which assets consume the cash. Untradable holdings remain
    untouched and require an explicitly supplied valuation price from caller.
    """
    qty = np.asarray(quantities, dtype=float).copy()
    target = np.asarray(target_weights, dtype=float)
    px = np.asarray(prices, dtype=float)
    count = len(symbols)
    if not 1 <= count <= 10 or len(set(symbols)) != count:
        raise ValueError("symbols must contain 1..10 unique assets")
    if any(x.shape != (count,) for x in (qty, target, px)) or len(asset_types) != count:
        raise ValueError("portfolio arrays must match symbols")
    if not math.isfinite(cash) or cash < 0:
        raise ValueError("cash must be finite and nonnegative")
    if not np.isfinite(qty).all() or (qty < 0).any():
        raise ValueError("quantities must be finite and nonnegative")
    if not np.isfinite(target).all() or (target < 0).any() or target.sum() > 1 + _EPS:
        raise ValueError("target weights must be nonnegative with sum <= 1")
    if not np.isfinite(px).all() or (px <= 0).any():
        raise ValueError("prices must be finite and positive")
    if not math.isfinite(band_pct) or not 0 <= band_pct <= 1:
        raise ValueError("band_pct must be finite and in [0, 1]")
    if not math.isfinite(min_trade_cny) or min_trade_cny < 0:
        raise ValueError("min_trade_cny must be finite and nonnegative")
    can_trade = np.ones(count, dtype=bool) if tradable is None else np.asarray(tradable)
    if can_trade.shape != (count,) or can_trade.dtype.kind != "b":
        raise ValueError("tradable must be a boolean per asset")
    commission = _rate(costs.commission_pct, "commission_pct")
    slippage = _rate(costs.slippage_pct, "slippage_pct")
    stamps = np.array([stamp_duty_rate(t, trade_date, costs) for t in asset_types])
    if (stamps + commission >= 1).any():
        raise ValueError("combined sell fee rate must be below 100%")
    cash = float(cash)
    nav = cash + float(qty @ px)
    if nav <= 0:
        raise ValueError("portfolio NAV must be positive")
    desired = target * nav / px
    change = desired - qty
    threshold = max(band_pct * nav, min_trade_cny)
    # Deterministic order also makes trade logs stable under array permutation.
    order = sorted(range(count), key=lambda i: symbols[i])
    fills: list[PortfolioFill] = []

    def fill(index: int, side: str, amount_qty: float) -> PortfolioFill:
        price = float(px[index] * (1 + slippage if side == "buy" else 1 - slippage))
        amount = amount_qty * price
        tax = amount * float(stamps[index]) if side == "sell" else 0.0
        return PortfolioFill(
            symbol=symbols[index], index=index, side=side, price=price,
            quantity=float(amount_qty), amount_cny=amount,
            commission_cny=amount * commission, stamp_duty_cny=tax,
            slippage_cny=amount_qty * abs(price - float(px[index])),
        )

    for i in order:
        if can_trade[i] and change[i] < -_EPS and -change[i] * px[i] >= threshold:
            sale = fill(i, "sell", min(float(-change[i]), float(qty[i])))
            qty[i] -= sale.quantity
            cash += sale.amount_cny - sale.fee_cny
            fills.append(sale)
    eligible = np.array([
        bool(can_trade[i] and change[i] > _EPS and change[i] * px[i] >= threshold)
        for i in range(count)
    ])
    buy_qty = np.where(eligible, np.maximum(change, 0.0), 0.0)
    required = float(np.sum(buy_qty * px * (1 + slippage) * (1 + commission)))
    factor = min(1.0, cash / required) if required > 0 else 0.0
    for i in order:
        quantity = float(buy_qty[i] * factor)
        if quantity <= _EPS:
            continue
        purchase = fill(i, "buy", quantity)
        cash -= purchase.amount_cny + purchase.fee_cny
        qty[i] += purchase.quantity
        fills.append(purchase)
    # Only roundoff residue is tolerated; affordability is enforced above.
    if cash < -max(1.0, nav) * 1e-12:
        raise ArithmeticError("shared portfolio spent more than available cash")
    return PortfolioExecution(cash=max(0.0, cash), quantities=qty, fills=tuple(fills))
