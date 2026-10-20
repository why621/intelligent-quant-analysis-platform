"""Shared-account switching invariants, independent of optional ML packages."""

from dataclasses import replace

import numpy as np
import pytest
from test_portfolio_rl import frames

from quant_platform.models import TradingCosts
from quant_platform.rl.changing_pool import ChangingPoolEpisode
from quant_platform.rl.errors import RLInsufficientHistory
from quant_platform.rl.portfolio_env import PortfolioEpisode


def episode(count=12, bars=8):
    source = frames(count, 180, flat=True)
    return ChangingPoolEpisode(
        source, asset_types=dict.fromkeys(source, "stock"),
        trading_costs=TradingCosts(0.03, 0.05, 0.02),
        random_start=False, episode_bars=bars,
    )


def invest(env, symbols):
    env.reset(options={"symbols": symbols})
    action = np.zeros(11)
    action[:len(symbols)] = 1
    env.step(action)


def test_complete_replacement_keeps_one_account_and_accounts_costs():
    env = episode()
    invest(env, ["A0", "A1"])
    before = env.account()
    obs, reward, done, _, info = env.switch_pool([f"A{i}" for i in range(2, 12)])
    assert not done and len(obs) == 161
    assert info["symbols"] == [f"A{i}" for i in range(2, 12)]
    assert info["quantities"] == [0] * 10
    assert len(info["fills"]) == 2 and all(f["side"] == "sell" for f in info["fills"])
    costs = (info["cumulativeFees"] - before["cumulativeFees"]
             + info["cumulativeSlippage"] - before["cumulativeSlippage"])
    assert info["equity"] == pytest.approx(before["equity"] - costs)
    assert reward == pytest.approx(np.log(info["equity"] / before["equity"]))
    _, _, _, _, traded = env.step(np.ones(11))
    assert traded["cash"] >= 0
    assert all(f["symbol"] in info["symbols"] for f in traded["fills"])


def test_retained_positions_follow_symbols_not_slots():
    env = episode()
    invest(env, ["A0", "A1", "A2"])
    quantity = env.quantities.copy()
    env.switch_pool(["A2", "A4", "A0"])
    np.testing.assert_array_equal(env.quantities, [quantity[2], 0, quantity[0]])
    assert env.account()["cash"] > 0


def test_suspended_exit_defers_whole_switch_then_retries():
    env = episode()
    invest(env, ["A0", "A1"])
    tradable = np.ones_like(env.panel.opens, dtype=bool)
    tradable[env.bar + 1, env.panel.indices(["A0"])] = False
    env.panel = replace(env.panel, tradable=tradable)
    before = env.account()
    _, reward, _, _, info = env.switch_pool(["A2", "A3"])
    assert info["poolTransition"]["status"] == "deferred"
    assert info["poolTransition"]["blockedExits"] == ["A0"]
    assert info["fills"] == [] and info["quantities"] == before["quantities"]
    assert info["equity"] == before["equity"] and reward == 0
    _, _, _, _, applied = env.switch_pool(["A2", "A3"])
    assert applied["poolTransition"]["status"] == "applied"
    assert applied["quantities"] == [0, 0]


@pytest.mark.parametrize("symbols", [["A1"], ["A1", "A1"], ["A1", "unknown"]])
def test_invalid_switch_does_not_mutate_account(symbols):
    env = episode()
    invest(env, ["A0", "A1"])
    before = env.account()
    with pytest.raises(ValueError):
        env.switch_pool(symbols)
    assert env.account() == before


def test_new_asset_requires_actual_history_at_request_time():
    env = episode()
    invest(env, ["A0", "A1"])
    observed = np.full_like(env.panel.opens, 180, dtype=int)
    observed[env.bar, env.panel.indices(["A2"])] = 139
    env.panel = replace(env.panel, observed_bars=observed)
    before = env.account()
    with pytest.raises(RLInsufficientHistory, match="warm-up"):
        env.switch_pool(["A2", "A3"])
    assert env.account() == before


def test_finished_episode_cannot_switch_and_reset_restores_account():
    env = episode(bars=2)
    invest(env, ["A0", "A1"])
    assert env.switch_pool(["A2", "A3"])[2]
    before = env.account()
    with pytest.raises(RuntimeError):
        env.switch_pool(["A0", "A1"])
    assert env.account() == before
    env.reset(options={"symbols": ["A0", "A1"]})
    assert env.account()["equity"] == env.initial_capital
    assert env.trade_count == 0


def test_no_switch_is_identical_to_original_environment():
    env = episode()
    original = PortfolioEpisode(
        env.panel, asset_types=env.asset_types, trading_costs=env.costs,
        random_start=False, episode_bars=8,
    )
    for instance in (env, original):
        instance.reset(seed=42, options={"symbols": ["A1", "A2"]})
    for _ in range(8):
        left, right = env.step(np.ones(11)), original.step(np.ones(11))
        np.testing.assert_array_equal(left[0], right[0])
        assert left[1:] == right[1:]


def test_ten_to_two_and_suspended_zero_position_do_not_block():
    env = episode()
    invest(env, [f"A{i}" for i in range(10)])
    kept = env.quantities[[9, 0]].copy()
    _, _, _, _, info = env.switch_pool(["A9", "A0"])
    np.testing.assert_array_equal(env.quantities, kept)
    assert len(info["fills"]) == 8
    env.reset(options={"symbols": ["A0", "A1"]})
    tradable = np.zeros_like(env.panel.opens, dtype=bool)
    env.panel = replace(env.panel, tradable=tradable)
    assert env.switch_pool(["A2", "A3"])[4]["poolTransition"]["status"] == "applied"


def test_gap_and_retained_mark_to_market_are_in_transition_reward():
    env = episode()
    invest(env, ["A0", "A1"])
    old = env.account()
    opens, closes = env.panel.opens.copy(), env.panel.closes.copy()
    next_bar = env.bar + 1
    first, second = env.indices
    opens[next_bar, first] = 9
    closes[next_bar, second] = 12
    env.panel = replace(env.panel, opens=opens, closes=closes)
    _, reward, _, _, info = env.switch_pool(["A1", "A2"])
    fee_delta = info["cumulativeFees"] - old["cumulativeFees"]
    slip_delta = info["cumulativeSlippage"] - old["cumulativeSlippage"]
    expected = (old["equity"] - old["quantities"][0]
                + 2 * old["quantities"][1] - fee_delta - slip_delta)
    assert info["equity"] == pytest.approx(expected)
    assert reward == pytest.approx(np.log(expected / old["equity"]))
