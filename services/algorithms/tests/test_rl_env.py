"""Gymnasium-dependent environment tests. Skipped without the ``[rl]`` extra."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("gymnasium")
pytestmark = pytest.mark.rl

from quant_platform.rl.env import TradingEnv  # noqa: E402


def _prices(n=80, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
        }
    )


def test_continuous_observation_shape_and_reset():
    env = TradingEnv(_prices(), discrete=False)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (env.observation_space.shape[0],)
    assert np.isfinite(obs).all()


def test_continuous_action_maps_to_weight():
    env = TradingEnv(_prices(), discrete=False)
    env.reset(seed=0)
    assert env._target_weight([0.42]) == pytest.approx(0.42)
    assert env._target_weight([1.7]) == pytest.approx(1.0)  # clipped, long-only
    assert env._target_weight([-0.3]) == pytest.approx(0.0)


def test_discrete_action_maps_to_flat_or_all_in():
    env = TradingEnv(_prices(), discrete=True)
    env.reset(seed=0)
    assert env._target_weight(0) == 0.0
    assert env._target_weight(1) == 1.0


def test_episode_terminates_and_is_deterministic():
    def rollout(seed):
        env = TradingEnv(_prices(), discrete=False)
        obs, _ = env.reset(seed=seed)
        total, steps = 0.0, 0
        done = False
        while not done:
            obs, r, done, _, _ = env.step(np.array([0.5], dtype=np.float32))
            total += r
            steps += 1
        return total, steps

    a = rollout(0)
    b = rollout(0)
    assert a == b
    assert a[1] > 0


@pytest.mark.parametrize("discrete", [False, True])
@pytest.mark.parametrize("capital", [1., 100000.])
def test_all_in_never_borrows_even_after_repeated_actions(discrete, capital):
    env = TradingEnv(_prices(), discrete=discrete, initial_capital=capital,
                     transaction_cost=.001, band_pct=0., min_trade_cny=0.)
    env.reset()
    done = False
    while not done:
        action = 1 if discrete else np.array([1.])
        obs, reward, done, _, _ = env.step(action)
        assert env._cash >= 0
        assert env._shares >= 0
        assert 0 <= env._weight() <= 1
        assert 0 <= obs[-1] <= 1
        assert np.isfinite(reward)


@pytest.mark.parametrize("discrete", [False, True])
@pytest.mark.parametrize("capital,band,minimum", [(1000., 0., 0.), (100000., .005, 100.)])
def test_training_equity_matches_engine_each_bar(discrete, capital, band, minimum):
    from quant_platform.backtesting.engine import BacktestEngine
    from quant_platform.models import TradingCosts

    frame = _prices(45)
    costs = TradingCosts(.2, .1, .3)
    env = TradingEnv(frame, discrete=discrete, initial_capital=capital,
                     trading_costs=costs, band_pct=band, min_trade_cny=minimum)
    env.reset()
    signals = pd.Series(0. if discrete else np.nan, index=frame.index)
    expected = {}
    for i in range(20, len(frame) - 1):
        w = [0., 1.][i % 2] if discrete else [.004, .8, 1., 0.][i % 4]
        signals.iloc[i] = (1. if w else -1.) if discrete else w
        env.step(int(w) if discrete else np.array([w]))
        expected[pd.Timestamp(frame.date.iloc[i + 1])] = (
            env._cash + env._shares * frame.close.iloc[i + 1]
        )
    _, equity = BacktestEngine(None, {})._simulate(
        "TEST", frame, signals, capital, costs,
        "discrete_hold" if discrete else "continuous_target_weight", band, minimum,
    )
    for day, value in expected.items():
        assert equity.loc[day] == pytest.approx(value, abs=1e-8)


@pytest.mark.parametrize("n", [0, 1, 20, 21])
def test_short_environment_fails_before_reset(n):
    from quant_platform.rl.errors import RLInsufficientHistory

    with pytest.raises(RLInsufficientHistory):
        TradingEnv(_prices(n))


def test_minimum_environment_has_one_step():
    env = TradingEnv(_prices(22))
    env.reset()
    _, reward, done, _, _ = env.step(np.array([.5]))
    assert done and np.isfinite(reward)
