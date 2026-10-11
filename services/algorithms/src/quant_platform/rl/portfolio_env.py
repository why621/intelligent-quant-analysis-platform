"""One shared account, concurrent market observations and joint allocation actions.

PortfolioEpisode has no gym/torch dependency and uses exactly the broker used by
web backtests. The optional Gymnasium adapter is only needed for actual learning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict

import numpy as np
import pandas as pd

from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import rebalance_portfolio
from quant_platform.rl.features import MIN_WARMUP
from quant_platform.rl.portfolio_features import (
    ACTION_SIZE,
    MAX_ASSETS,
    MIN_ASSETS,
    OBSERVATION_SIZE,
    PortfolioPanel,
    action_weights,
    encode_observation,
    prepare_panel,
)


class PortfolioEpisode:
    """Dependency-light state machine; a reset starts a new shared cash account."""

    def __init__(
        self,
        frames: Mapping[str, pd.DataFrame] | PortfolioPanel,
        *,
        asset_types: Mapping[str, str],
        trading_costs: TradingCosts,
        initial_capital: float = 100_000.0,
        random_subsets: bool = True,
        random_start: bool = True,
        episode_bars: int = 64,
        min_assets: int = MIN_ASSETS,
        max_assets: int = MAX_ASSETS,
        band_pct: float = 0.0,
        min_trade_cny: float = 0.0,
    ) -> None:
        self.panel = frames if isinstance(frames, PortfolioPanel) else prepare_panel(frames)
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError("initial capital must be finite and positive")
        if not MIN_ASSETS <= min_assets <= max_assets <= MAX_ASSETS:
            raise ValueError("episode asset count must be within two to ten")
        if len(self.panel.symbols) < min_assets:
            raise ValueError("training pool is smaller than the minimum episode asset count")
        if not isinstance(episode_bars, int) or isinstance(episode_bars, bool) or episode_bars < 1:
            raise ValueError("episode_bars must be a positive integer")
        if episode_bars > len(self.panel.dates) - MIN_WARMUP - 1:
            raise ValueError("insufficient common history after warm-up for the episode")
        if any(asset_types.get(symbol) not in ("stock", "etf") for symbol in self.panel.symbols):
            raise ValueError("every asset must explicitly declare stock or etf")
        for value in (band_pct, min_trade_cny):
            if not np.isfinite(value) or value < 0:
                raise ValueError("rebalance thresholds must be finite and nonnegative")
        self.asset_types = dict(asset_types)
        self.costs = trading_costs
        self.initial_capital = float(initial_capital)
        self.random_subsets = random_subsets
        self.random_start = random_start
        self.episode_bars = episode_bars
        self.min_assets = min_assets
        self.max_assets = min(max_assets, len(self.panel.symbols))
        self.band_pct = band_pct
        self.min_trade_cny = min_trade_cny
        self.rng = np.random.default_rng()
        self.episode_count = 0
        self.sample_log: list[dict] = []
        self._ready = False

    def reset(self, *, seed: int | None = None, options: Mapping | None = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        options = dict(options or {})
        if set(options) - {"symbols", "start_index"}:
            raise ValueError("unknown portfolio reset option")
        if "symbols" in options:
            symbols = tuple(options["symbols"])
            if not MIN_ASSETS <= len(symbols) <= MAX_ASSETS or len(set(symbols)) != len(symbols):
                raise ValueError("episode symbols must be two to ten distinct assets")
        elif self.random_subsets:
            count = int(self.rng.integers(self.min_assets, self.max_assets + 1))
            symbols = tuple(self.rng.choice(self.panel.symbols, count, replace=False).tolist())
        else:
            if len(self.panel.symbols) > MAX_ASSETS:
                raise ValueError(
                    "fixed episode requires at most ten assets; none are silently dropped"
                )
            symbols = self.panel.symbols
        self.indices = self.panel.indices(symbols)
        last_start = len(self.panel.dates) - self.episode_bars - 1
        start = options.get("start_index")
        if start is None:
            start = (
                int(self.rng.integers(MIN_WARMUP, last_start + 1))
                if self.random_start
                else (MIN_WARMUP)
            )
        if (
            not isinstance(start, (int, np.integer))
            or isinstance(start, bool)
            or not MIN_WARMUP <= start <= last_start
        ):
            raise ValueError("episode start must leave full warm-up and requested future bars")
        self.symbols = symbols
        self.bar = int(start)
        self.end_bar = self.bar + self.episode_bars
        self.cash = self.initial_capital
        self.quantities = np.zeros(len(symbols), dtype=float)
        self.cumulative_fees = 0.0
        self.cumulative_slippage = 0.0
        self.trade_count = 0
        self.episode_count += 1
        self._ready = True
        context = {
            "symbols": list(symbols),
            "startDate": self.panel.dates[self.bar].date().isoformat(),
            "endDate": self.panel.dates[self.end_bar].date().isoformat(),
        }
        # Bounded evidence, not a potentially unbounded training-memory leak.
        if len(self.sample_log) < 256:
            self.sample_log.append(context)
        return self.observation(), {"episode": context, **self.account()}

    def observation(self) -> np.ndarray:
        if not self._ready:
            raise RuntimeError("reset the portfolio episode before observing")
        return encode_observation(
            self.panel.features[self.bar, self.indices],
            self.quantities,
            self.panel.closes[self.bar, self.indices],
            self.cash,
        )

    def account(self) -> dict:
        values = self.quantities * self.panel.closes[self.bar, self.indices]
        equity = float(self.cash + values.sum())
        return {
            "date": self.panel.dates[self.bar].date().isoformat(),
            "symbols": list(self.symbols),
            "cash": float(self.cash),
            "quantities": self.quantities.tolist(),
            "equity": equity,
            "weights": (values / equity).tolist(),
            "cashWeight": float(self.cash / equity),
            "cumulativeFees": self.cumulative_fees,
            "cumulativeSlippage": self.cumulative_slippage,
            "tradeCount": self.trade_count,
        }

    def step(self, action: Sequence[float]):
        if not self._ready or self.bar >= self.end_bar:
            raise RuntimeError("reset required before stepping a new or finished episode")
        weights = action_weights(action, len(self.symbols))
        before = self.account()["equity"]
        next_bar = self.bar + 1
        result = rebalance_portfolio(
            cash=self.cash,
            quantities=self.quantities,
            target_weights=weights[: len(self.symbols)],
            prices=self.panel.opens[next_bar, self.indices],
            symbols=self.symbols,
            asset_types=[self.asset_types[symbol] for symbol in self.symbols],
            trade_date=self.panel.dates[next_bar].date(),
            costs=self.costs,
            band_pct=self.band_pct,
            min_trade_cny=self.min_trade_cny,
        )
        self.cash, self.quantities = result.cash, result.quantities.copy()
        self.bar = next_bar
        self.trade_count += len(result.fills)
        self.cumulative_fees += sum(fill.fee_cny for fill in result.fills)
        self.cumulative_slippage += sum(fill.slippage_cny for fill in result.fills)
        info = self.account()
        info["targetWeights"] = weights.tolist()
        info["fills"] = [asdict(fill) for fill in result.fills]
        reward = float(np.log(info["equity"] / before))
        terminated = self.bar >= self.end_bar
        return self.observation(), reward, terminated, False, info


def make_portfolio_env(*args, **kwargs):
    """Construct the optional Gym adapter without importing ML in offline code."""
    try:
        import gymnasium as gym
        from gymnasium import spaces
    except ImportError as exc:
        from quant_platform.rl.errors import RLDependenciesMissing

        raise RLDependenciesMissing(
            "joint training requires the optional [rl] dependencies"
        ) from exc

    class PortfolioTradingEnv(gym.Env):
        metadata = {"render_modes": []}

        def __init__(self):
            super().__init__()
            self.episode = PortfolioEpisode(*args, **kwargs)
            self.action_space = spaces.Box(0.0, 1.0, shape=(ACTION_SIZE,), dtype=np.float32)
            self.observation_space = spaces.Box(
                -np.inf,
                np.inf,
                shape=(OBSERVATION_SIZE,),
                dtype=np.float32,
            )

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return self.episode.reset(seed=seed, options=options)

        def step(self, action):
            return self.episode.step(action)

    return PortfolioTradingEnv()
