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
