from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import (
    rebalance_portfolio,
    signal_target_weights,
    stamp_duty_rate,
)


def execute(**changes):
    args = dict(
        cash=1000.0, quantities=[0.0, 0.0], target_weights=[0.5, 0.5],
        prices=[10.0, 20.0], symbols=["000001", "510300"],
        asset_types=["stock", "etf"], trade_date=date(2026, 10, 9),
        costs=TradingCosts(0, 0, 0),
    )
    args.update(changes)
    return rebalance_portfolio(**args)


def test_sale_proceeds_fund_another_asset_in_one_ledger():
    first = execute(target_weights=[1, 0])
    second = execute(cash=first.cash, quantities=first.quantities, target_weights=[0, 1])
    assert first.quantities.tolist() == [100, 0]
    assert second.quantities.tolist() == [0, 50]
    assert second.cash == 0
    assert [(f.symbol, f.side) for f in second.fills] == [
        ("000001", "sell"), ("510300", "buy")
    ]


def test_one_cash_budget_and_no_double_charge_for_slippage():
    result = execute(costs=TradingCosts(0.03, 0.05, 0.02))
    fees = sum(f.fee_cny for f in result.fills)
    slippage = sum(f.slippage_cny for f in result.fills)
    marked_value = result.cash + result.quantities @ np.array([10, 20])
    assert result.cash >= 0
    assert marked_value == pytest.approx(1000 - fees - slippage)
    assert result.quantities[0] * 10 == pytest.approx(result.quantities[1] * 20)
    assert all(f.stamp_duty_cny == 0 for f in result.fills)


def test_ten_assets_receive_one_initial_capital_not_ten_accounts():
    result = execute(
        symbols=[f"{i:06d}" for i in range(10)], asset_types=["etf"] * 10,
        quantities=[0] * 10, prices=[10] * 10, target_weights=[0.1] * 10,
    )
    assert result.quantities.tolist() == pytest.approx([10] * 10)
    assert result.cash + result.quantities.sum() * 10 == pytest.approx(1000)


def test_permuting_input_does_not_change_symbol_execution():
    a = execute(cash=200, quantities=[50, 15], target_weights=[0.2, 0.8],
                costs=TradingCosts(0.03, 0.05, 0.02))
    b = execute(cash=200, quantities=[15, 50], target_weights=[0.8, 0.2],
                symbols=["510300", "000001"], asset_types=["etf", "stock"],
                prices=[20, 10], costs=TradingCosts(0.03, 0.05, 0.02))
    assert a.cash == pytest.approx(b.cash)
    assert a.quantities == pytest.approx(b.quantities[::-1])
    assert [(f.symbol, f.side, f.amount_cny) for f in a.fills] == [
        (f.symbol, f.side, f.amount_cny) for f in b.fills
    ]


def test_suspended_asset_is_valued_but_cannot_be_sold_to_fund_buy():
    result = execute(cash=0, quantities=[100, 0], target_weights=[0, 1],
                     tradable=[False, True])
    assert result.quantities.tolist() == [100, 0]
    assert result.fills == ()


def test_hold_does_not_create_position_or_daily_rebalance():
    assert signal_target_weights([0, 0], [0, 0]).tolist() == [0, 0]
    assert signal_target_weights([0, 0], [0.3, 0.6]).tolist() == [0.3, 0.6]
    assert signal_target_weights([1, 0], [0, 0], cash_pct=10).tolist() == [0.9, 0]
    assert signal_target_weights([1, 0], [0, 0.6], cash_pct=10).tolist() == [0.45, 0.45]
    assert signal_target_weights([-1, 0], [0.5, 0.5]).tolist() == [0, 1]


def test_asset_date_tax_switch_and_explicit_fixed_experiment():
    auto = SimpleNamespace(stamp_duty_mode="asset_date", stamp_duty_pct=12)
    assert stamp_duty_rate("etf", date(2020, 1, 1), auto) == 0
    assert stamp_duty_rate("stock", date(2023, 8, 25), auto) == 0.001
    assert stamp_duty_rate("stock", date(2023, 8, 28), auto) == 0.0005
    assert stamp_duty_rate("etf", date(2020, 1, 1), TradingCosts()) == 0.0005
    with pytest.raises(ValueError, match="2008"):
        stamp_duty_rate("stock", date(2000, 1, 1), auto)


def test_selling_cost_breakdown_matches_cash_and_marked_value():
    costs = SimpleNamespace(commission_pct=0.03, slippage_pct=0.02,
                            stamp_duty_pct=0.05, stamp_duty_mode="asset_date")
    result = execute(cash=0, quantities=[50, 25], target_weights=[0, 0], costs=costs)
    assert result.cash == pytest.approx(1000 - sum(f.total_cost_cny for f in result.fills))
    assert result.quantities.tolist() == [0, 0]
    assert result.fills[0].stamp_duty_cny > 0
    assert result.fills[1].stamp_duty_cny == 0


@pytest.mark.parametrize("changes", [
    {"cash": -1}, {"target_weights": [0.8, 0.8]}, {"target_weights": [float("nan"), 0]},
    {"prices": [0, 20]}, {"quantities": [-1, 0]}, {"symbols": ["510300", "510300"]},
    {"tradable": [1, 0]}, {"band_pct": float("inf")}, {"asset_types": ["stock", "unknown"]},
])
def test_invalid_joint_order_is_rejected(changes):
    with pytest.raises(ValueError):
        execute(**changes)
