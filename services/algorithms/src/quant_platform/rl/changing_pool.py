"""Research-only exogenous pool transitions; production environments are unchanged."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from quant_platform.portfolio.execution import rebalance_portfolio
from quant_platform.rl.features import MIN_WARMUP
from quant_platform.rl.portfolio_env import PortfolioEpisode
from quant_platform.rl.portfolio_features import MAX_ASSETS, MIN_ASSETS, insufficient_history


class ChangingPoolEpisode(PortfolioEpisode):
    """Switch requests consume one session, with no model action on that session.

    Retained positions are untouched. New positions start at zero. If an exit
    position is suspended, the entire switch is deferred and the old account is
    marked to the next close. Callers explicitly retry; there is no hidden order.
    """

    def switch_pool(self, symbols):
        if not self._ready or self.bar >= self.end_bar:
            raise RuntimeError("reset required before switching a new or finished episode")
        proposed = tuple(symbols)
        if (not MIN_ASSETS <= len(proposed) <= MAX_ASSETS
                or len(set(proposed)) != len(proposed)):
            raise ValueError("pool must contain two to ten distinct assets")
        indices = self.panel.indices(proposed)
        if self.panel.observed_bars is not None and np.any(
            self.panel.observed_bars[self.bar, indices] <= MIN_WARMUP
        ):
            raise insufficient_history("new pool requires actual warm-up before request")
        old_symbols = self.symbols
        old_quantities = dict(zip(old_symbols, self.quantities, strict=True))
        exiting = np.array([s not in proposed for s in old_symbols])
        next_bar = self.bar + 1
        tradable = (np.ones(len(old_symbols), dtype=bool) if self.panel.tradable is None
                    else self.panel.tradable[next_bar, self.indices])
        blocked = exiting & (self.quantities > 0) & ~tradable
        before = self.account()["equity"]
        fills = []
        if not blocked.any():
            # The broker only sees the old <=10 slots, never the union of both pools.
            # Only exiting slots are eligible for execution, so retained positions
            # cannot incur even a roundoff-sized trade or an extra commission.
            prices = self.panel.opens[next_bar, self.indices]
            result = rebalance_portfolio(
                cash=self.cash, quantities=self.quantities,
                target_weights=np.zeros(len(old_symbols)),
                prices=prices, symbols=old_symbols,
                asset_types=[self.asset_types[s] for s in old_symbols],
                trade_date=self.panel.dates[next_bar].date(), costs=self.costs,
                tradable=tradable & exiting,
            )
            if np.any(result.quantities[exiting] != 0):
                raise ArithmeticError("exit residue cannot be silently removed from account")
            # No mutations occur until execution and all invariants have passed.
            retained = ~exiting
            if not np.array_equal(result.quantities[retained], self.quantities[retained]):
                raise ArithmeticError("pool switch changed retained quantities")
            self.cash = result.cash
            self.symbols = proposed
            self.indices = indices
            self.quantities = np.array([old_quantities.get(s, 0.0) for s in proposed])
            fills = [asdict(fill) for fill in result.fills]
            self.cumulative_fees += sum(fill.fee_cny for fill in result.fills)
            self.cumulative_slippage += sum(fill.slippage_cny for fill in result.fills)
            self.trade_count += len(result.fills)
        self.bar = next_bar
        info = self.account()
        info["fills"] = fills
        info["poolTransition"] = {
            "status": "deferred" if blocked.any() else "applied",
            "previousSymbols": list(old_symbols), "requestedSymbols": list(proposed),
            "blockedExits": [s for s, b in zip(old_symbols, blocked, strict=True) if b],
            "actionApplied": False, "retryRequired": bool(blocked.any()),
            "fillIndexSymbols": list(old_symbols),
        }
        return (self.observation(), float(np.log(info["equity"] / before)),
                self.bar >= self.end_bar, False, info)
