"""Gymnasium trading environment built from the repo's own OHLC frames.

Deliberately NOT a copy of FinRL's training scripts (which are known to leak):
the agent acts on bar *t*'s close, the fill happens at bar *t+1*'s open, and
the state is only ever a function of rows ``<= t``. This module imports
gymnasium at module scope and is therefore only reachable from the training /
model-loading paths — never from the default dependency-free test-suite.

CR-059 additions, each aimed at a measured defect rather than a hope:

* ``reward_mode`` — ``log_return`` (unchanged default, kept bit-for-bit so old
  runs stay comparable), ``excess`` (portfolio minus the asset's own close-to-close
  log return, i.e. the buy-and-hold reward the grid scores against), and ``dsr``
  (Moody & Saffell's differential Sharpe ratio, the literature's risk-adjusted
  alternative to raw profit).
* ``turnover_penalty`` — subtracts the fee fraction a second time, scaled by the
  caller. The fee is already inside the portfolio return, but with gamma=0.99 the
  discounted cost drag of churn is ~100 bars away; this makes it immediate.
* ``random_start`` — every reset picks a fresh start offset. Previously the start
  was fixed, so the agent re-walked one identical deterministic path 186 times.
* DQN gets a three-way action (flat / hold / all-in). "hold" emits signal 0.0,
  which ``execute_bar`` treats as no order, so the discrete cost convention and
  ``SignalSemantics.DISCRETE_HOLD`` are untouched.
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from quant_platform.backtesting.execution import execute_bar
from quant_platform.models import TradingCosts
from quant_platform.rl.features import (
    MIN_WARMUP,
    build_observations,
    validate_history,
)

_LONG_ONLY_WEIGHTS = (0.0, 1.0)
# Discrete actions: 0 = go flat, 1 = hold (no order), 2 = go all-in.
_DISCRETE_FLAT = 0
_DISCRETE_HOLD = 1
_DISCRETE_ALL_IN = 2
DISCRETE_ACTIONS = 3

REWARD_MODES = ("log_return", "excess", "dsr")
# DSR is var/denominator normalised, so a quiet stretch can spike it; bound it.
_DSR_CLIP = 10.0
DEFAULT_DSR_ETA = 0.01


class TradingEnv(gym.Env):
    """Single-asset, long-only, target-weight environment.

    Args:
        prices: date-ordered ``open/high/low/close`` frame for one asset.
        discrete: emit a 3-way {flat, hold, all-in} action (DQN) instead of a
            continuous target weight (PPO/SAC/DDPG/TD3).
        transaction_cost: proportional cost charged on the traded notional.
        reward_mode: one of ``REWARD_MODES``.
        turnover_penalty: extra multiple of the fee fraction subtracted from the
            reward; 0.0 reproduces the pre-CR-059 reward exactly.
        random_start: sample the episode start offset on every reset.
        min_episode_bars: floor on the episode length when ``random_start`` is on.
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
        band_pct: float = 0.02,
        min_trade_cny: float = 100.0,
        reward_mode: str = "log_return",
        turnover_penalty: float = 0.0,
        dsr_eta: float = DEFAULT_DSR_ETA,
        random_start: bool = False,
        min_episode_bars: int = 250,
    ) -> None:
        super().__init__()
        validate_history(prices, window)
        if not np.isfinite(initial_capital) or initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if reward_mode not in REWARD_MODES:
            raise ValueError(f"reward_mode 必须是 {REWARD_MODES} 之一，实际 {reward_mode!r}")
        if not np.isfinite(turnover_penalty) or turnover_penalty < 0:
            raise ValueError("turnover_penalty must be finite and >= 0")
        if not np.isfinite(dsr_eta) or not 0.0 < dsr_eta <= 1.0:
            raise ValueError("dsr_eta must be in (0, 1]")
        self._capital = initial_capital
        self._band = band_pct
        self._min_trade = min_trade_cny
        self._raw = prices.reset_index(drop=True)
        self._features = build_observations(self._raw, window=window)
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
        self._reward_mode = reward_mode
        self._turnover_penalty = float(turnover_penalty)
        self._dsr_eta = float(dsr_eta)
        # Start after the full feature+warm-up so every observation is finite and
        # frame-origin-independent, matching serve.
        self._first = max(MIN_WARMUP, window)
        self._last = len(self._raw) - 1
        self._random_start = bool(random_start)
        self._min_episode_bars = int(min_episode_bars)
        if self._random_start:
            if self._min_episode_bars < 1:
                raise ValueError("min_episode_bars must be >= 1")
            if self._last - self._min_episode_bars < self._first:
                raise ValueError(
                    f"随机起点需要至少 {self._first + self._min_episode_bars + 1} 根行情"
                    f"（预热 {self._first} + 最短 episode {self._min_episode_bars}），"
                    f"实际 {len(self._raw)} 根"
                )

        obs_dim = self._features.shape[1] + 1  # features + current weight
        high = np.full(obs_dim, np.inf)
        self.observation_space = spaces.Box(-high, high, dtype=np.float32)
        if discrete:
            self.action_space = spaces.Discrete(DISCRETE_ACTIONS)
        else:
            self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        self._step_index = self._first
        self._cash = self._capital
        self._shares = 0.0
        self._moment_a = 0.0
        self._moment_b = 0.0

    def _weight(self) -> float:
        price = self._close[self._step_index]
        return float(self._shares * price / (self._cash + self._shares * price))

    def _observation(self) -> np.ndarray:
        vec = self._features[self._step_index]
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        return np.concatenate([vec.astype(np.float32), [np.float32(self._weight())]])

    def _start_index(self, *, random_start: bool) -> int:
        if not random_start:
            return self._first
        high = self._last - self._min_episode_bars
        return int(self.np_random.integers(self._first, high + 1))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_index = self._start_index(random_start=self._random_start)
        self._cash = self._capital
        self._shares = 0.0
        self._moment_a = 0.0
        self._moment_b = 0.0
        return self._observation(), {}

    def _discrete_command(self, action) -> float:
        """Map a discrete action to the engine's signal for ``discrete_hold``."""
        index = int(action)
        if index == _DISCRETE_HOLD:
            # execute_bar returns no fill for any signal outside {+1, -1}, and a
            # hold must not trade at all — not even a banded rebalance.
            return 0.0
        return 1.0 if index == _DISCRETE_ALL_IN else -1.0

    def _command(self, action) -> float:
        if self._discrete:
            return self._discrete_command(action)
        return float(np.clip(np.asarray(action, dtype=float).reshape(-1)[0], 0.0, 1.0))

    def _dsr(self, log_return: float) -> float:
        """Moody & Saffell (1998) differential Sharpe ratio, bounded for stability."""
        prev_a, prev_b = self._moment_a, self._moment_b
        delta_a = log_return - prev_a
        delta_b = log_return * log_return - prev_b
        self._moment_a = prev_a + self._dsr_eta * delta_a
        self._moment_b = prev_b + self._dsr_eta * delta_b
        variance = prev_b - prev_a * prev_a
        if variance <= 0.0:
            return 0.0
        value = (prev_b * delta_a - 0.5 * prev_a * delta_b) / variance**1.5
        return float(np.clip(value, -_DSR_CLIP, _DSR_CLIP))

    def _reward(self, equity_before: float, equity_after: float, fee: float, i: int) -> float:
        if equity_before <= 0.0:
            return 0.0
        log_return = float(np.log(equity_after / equity_before))
        if self._turnover_penalty:
            log_return -= self._turnover_penalty * fee / equity_before
        if self._reward_mode == "log_return":
            return log_return
        if self._reward_mode == "excess":
            market = float(np.log(self._close[i + 1] / self._close[i]))
            return log_return - market
        return self._dsr(log_return)

    def step(self, action):
        i = self._step_index
        equity_before = self._cash + self._shares * self._close[i]

        self._cash, self._shares, fill = execute_bar(
            self._cash,
            self._shares,
            self._command(action),
            self._close[i],
            self._open[i + 1],
            semantics="discrete_hold" if self._discrete else "continuous_target_weight",
            commission=self._commission,
            stamp=self._stamp,
            slippage=self._slippage,
            band_pct=self._band,
            min_trade_cny=self._min_trade,
        )

        self._step_index = i + 1
        done = self._step_index >= self._last
        equity_after = self._cash + self._shares * self._close[self._step_index]
        fee = float(fill.fee) if fill is not None else 0.0
        reward = self._reward(equity_before, equity_after, fee, i)
        return self._observation(), reward, bool(done), False, {}