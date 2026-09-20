"""Single-bar cash execution shared by backtests and RL training (no ML imports)."""
from dataclasses import dataclass

EXECUTION_VERSION = "account-feedback-v2"


@dataclass(frozen=True)
class Fill:
    side: str
    price: float
    quantity: float
    amount: float
    fee: float


def execute_bar(cash, shares, signal, close, next_open, *, semantics,
                commission, stamp, slippage, band_pct=0.005, min_trade_cny=100.0):
    """Execute a close decision at the following open, without borrowing cash."""
    if semantics != "continuous_target_weight":
        # Preserve the established discrete strategy commission convention.
        if signal == 1.0 and cash > 0:
            price = next_open * (1 + slippage)
            fee = cash * commission
            invest = cash - fee
            shares = invest / price
            return 0.0, shares, Fill("buy", price, shares, invest, fee)
        if signal == -1.0 and shares > 0:
            price = next_open * (1 - slippage)
            gross = shares * price
            fee = gross * (commission + stamp)
            return gross - fee, 0.0, Fill("sell", price, shares, gross, fee)
        return cash, shares, None

    equity = cash + shares * close
    delta = signal * equity - shares * next_open
    band = max(band_pct * equity, min_trade_cny)
    if delta > 0 and delta >= band and cash > 0:
        price = next_open * (1 + slippage)
        amount = min(delta, cash / (1 + commission))
        quantity = amount / price
        fee = amount * commission
        # Only floating-point subtraction residue can be clipped here: the
        # affordability bound above includes the fee before computing quantity.
        return max(0.0, cash - amount - fee), shares + quantity, Fill(
            "buy", price, quantity, amount, fee
        )
    if delta < 0 and delta <= -band and shares > 0:
        price = next_open * (1 - slippage)
        quantity = min(-delta / price, shares)
        amount = quantity * price
        fee = amount * (commission + stamp)
        return cash + amount - fee, shares - quantity, Fill(
            "sell", price, quantity, amount, fee
        )
    return cash, shares, None
