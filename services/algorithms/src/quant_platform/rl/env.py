"""Gymnasium trading environment built from the repo's own OHLC frames.

Deliberately NOT a copy of FinRL's training scripts (which are known to leak):
the agent acts on bar *t*'s close, the fill happens at bar *t+1*'s open, and
the state is only ever a function of rows ``<= t``. This module imports
gymnasium at module scope and is therefore only reachable from the training /
model-loading paths — never from the default dependency-free test-suite.
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from quant_platform.backtesting.execution import execute_bar
from quant_platform.models import TradingCosts
from quant_platform.rl.features import build_features, expanding_zscore, validate_history

_LONG_ONLY_WEIGHTS = (0.0, 1.0)


class TradingEnv(gym.Env):
    """Single-asset, long-only, target-weight environment.

    Args:
        prices: date-ordered ``open/high/low/close`` frame for one asset.
        discrete: emit a 2-way {flat, all-in} action (DQN) instead of a
            continuous target weight (PPO/SAC/DDPG).
        transaction_cost: proportional cost charged on the traded notional.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        prices: pd.DataFrame,
        *,
        discrete: bool = False,
        window: int = 20,
        transaction_cost: float | None = None,
        initial_capital: float = 100_000.0,
        trading_costs: TradingCosts | None = None,
        band_pct: float = 0.005,
        min_trade_cny: float = 100.0,
    ) -> None:
        super().__init__()
        validate_history(prices, window)
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self._capital = initial_capital
        self._band = band_pct
        self._min_trade = min_trade_cny
        self._raw = prices.reset_index(drop=True)
        self._features = expanding_zscore(build_features(self._raw, window=window))
        self._open = self._raw["open"].to_numpy(dtype=float)
        self._close = self._raw["close"].to_numpy(dtype=float)
        self._discrete = discrete
        costs = trading_costs or TradingCosts()
        self._commission = costs.commission_pct / 100
        self._stamp = costs.stamp_duty_pct / 100
        self._slippage = costs.slippage_pct / 100
        if transaction_cost is not None:
            if not np.isfinite(transaction_cost) or not 0 <= transaction_cost < 1:
                raise ValueError("transaction_cost must be in [0, 1)")
            self._commission, self._stamp, self._slippage = float(transaction_cost), 0.0, 0.0
        # Start after the feature warm-up so the first observation is finite.
        self._first = max(window, 1)
        self._last = len(self._raw) - 1

        obs_dim = self._features.shape[1] + 1  # features + current weight
        high = np.full(obs_dim, np.inf)
        self.observation_space = spaces.Box(-high, high, dtype=np.float32)
        if discrete:
            self.action_space = spaces.Discrete(2)
        else:
            self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        self._step_index = self._first
        self._cash = self._capital
        self._shares = 0.0

    def _weight(self) -> float:
        price = self._close[self._step_index]
        return float(self._shares * price / (self._cash + self._shares * price))

    def _observation(self) -> np.ndarray:
        vec = self._features[self._step_index]
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        return np.concatenate([vec.astype(np.float32), [np.float32(self._weight())]])

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_index = self._first
        self._cash = self._capital
        self._shares = 0.0
        return self._observation(), {}

    def _target_weight(self, action) -> float:
        if self._discrete:
            return _LONG_ONLY_WEIGHTS[int(action)]
        return float(np.clip(np.asarray(action, dtype=float).reshape(-1)[0], 0.0, 1.0))

    def step(self, action):
        i = self._step_index
        equity_before = self._cash + self._shares * self._close[i]
        w = self._target_weight(action)

        signal = (1.0 if w else -1.0) if self._discrete else w
        self._cash, self._shares, _ = execute_bar(
            self._cash, self._shares, signal, self._close[i], self._open[i + 1],
            semantics="discrete_hold" if self._discrete else "continuous_target_weight",
            commission=self._commission, stamp=self._stamp, slippage=self._slippage,
            band_pct=self._band, min_trade_cny=self._min_trade,
        )

        self._step_index = i + 1
        done = self._step_index >= self._last
        equity_after = self._cash + self._shares * self._close[self._step_index]
        reward = float(np.log(equity_after / equity_before)) if equity_before > 0 else 0.0
        return self._observation(), reward, bool(done), False, {}
