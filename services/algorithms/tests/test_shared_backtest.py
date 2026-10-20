from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_platform.allocation import AllocationService
from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.models import Asset, BacktestRequest, DataStatus, StrategyInfo, TradingCosts


class Provider:
    def __init__(self, levels=None, count=4):
        self.dates = pd.date_range(end="2026-08-21", periods=count, freq="B")
        self.frames = {}
        for symbol, base in (("510300", 10), ("600000", 20)):
            values = (levels or {}).get(symbol, [base] * count)
            self.frames[symbol] = pd.DataFrame({
                "date": self.dates, "open": values, "close": values,
                "high": values, "low": values, "volume": [1000] * count,
            })

    def history(self, symbol, start, end, adjust="qfq"):
        return self.frames[symbol].copy()

    def list_assets(self, **kwargs):
        return [Asset("510300", "ETF", "etf", "SSE"),
                Asset("600000", "Stock", "stock", "SSE")]

    def status(self):
        return DataStatus("ready", "fixture", 2, date(2026, 8, 21), None)


class Rules:
    def __init__(self, kind="rotate"):
        self.kind = kind

    def info(self):
        return StrategyInfo("rules", "rules", "traditional", "available", "fixture")

    def validate_parameters(self, parameters):
        pass

    def generate_signals(self, frame, parameters):
        values = [0.0] * len(frame)
        if self.kind == "neutral":
            return pd.Series(values)
        asset_a = frame["open"].iloc[0] == 10
        values[0] = 1.0 if asset_a else 0.0
        if self.kind == "rotate":
            values[1] = -1.0 if asset_a else 1.0
        return pd.Series(values)


def request(**kwargs):
    return replace(BacktestRequest(
        symbols=("510300", "600000"), strategy_id="rules",
        start_date=date(2026, 7, 1), end_date=date(2026, 8, 21),
        initial_capital_cny=1000, trading_costs=TradingCosts(0, 0, 0),
        portfolio_mode="shared_account", benchmark_mode="buy_and_hold",
    ), **kwargs)


def test_cash_moves_between_assets_in_one_account():
    result = BacktestEngine(Provider(), {"rules": Rules()}).run(request())
    assert [(t.symbol, t.side) for t in result.trades] == [
        ("510300", "buy"), ("510300", "sell"), ("600000", "buy")]
    assert result.trades[-1].amount_cny == pytest.approx(1000)
    for point in result.account_curve:
        assert point["cashCny"] >= 0
        assert point["equity"] == pytest.approx(point["cashCny"] + sum(
            p["marketValueCny"] for p in point["positions"]))
    assert result.cost_summary["tradeCount"] == 3
    assert result.benchmark_context["costsIncluded"] is False
    assert result.equity_curve["benchmarkEquity"].tolist() == [1, 1, 1, 1]


def test_hold_does_not_rebalance_after_overnight_gap():
    provider = Provider({"510300": [10, 10, 20, 30]})
    result = BacktestEngine(provider, {"rules": Rules("hold")}).run(request(cash_pct=50))
    assert len(result.trades) == 1
    assert result.account_curve[-1]["cashCny"] == pytest.approx(500)
    assert result.account_curve[-1]["positions"][0]["quantity"] == pytest.approx(50)
    assert result.account_curve[-1]["equity"] == pytest.approx(2000)


def test_symbol_order_preserves_cash_equity_and_costs():
    engine = BacktestEngine(Provider(), {"rules": Rules()})
    costs = TradingCosts(0.03, 0.05, 0.02, "asset_date")
    first = engine.run(request(trading_costs=costs))
    second = engine.run(request(symbols=("600000", "510300"), trading_costs=costs))
    assert first.equity_curve["equity"].tolist() == pytest.approx(second.equity_curve["equity"])
    assert first.cost_summary == pytest.approx(second.cost_summary)
    assert first.trades[1].stamp_duty_cny == 0  # ETF sell, not stock tax.
    assert first.cost_summary["feesCny"] == pytest.approx(sum(t.fee_cny for t in first.trades))
    assert first.cost_summary["totalTradingCostCny"] == pytest.approx(
        first.cost_summary["feesCny"] + first.cost_summary["slippageCny"])


def test_buy_hold_benchmark_is_bitwise_stable_under_asset_permutations():
    provider = Provider()
    rng = np.random.default_rng(42)
    provider.frames = {
        str(symbol): pd.DataFrame({"date": provider.dates, "close": rng.uniform(1, 100, 4)})
        for symbol in range(10)
    }
    engine = BacktestEngine(provider, {"rules": Rules()})
    symbols = tuple(provider.frames)
    expected = engine._benchmark_curve(request(symbols=symbols), provider.dates)
    for permutation in [symbols[::-1], *[tuple(rng.permutation(symbols)) for _ in range(8)]]:
        actual = engine._benchmark_curve(request(symbols=permutation), provider.dates)
        pd.testing.assert_series_equal(expected, actual, check_exact=True)


def test_buy_hold_is_initial_equal_hold_not_daily_rebalance():
    provider = Provider({"510300": [10, 20, 10, 40], "600000": [20, 20, 40, 20]})
    result = BacktestEngine(provider, {"rules": Rules("neutral")}).run(request())
    assert result.equity_curve["benchmarkEquity"].tolist() == pytest.approx([1, 1.5, 1.5, 2.5])
    assert result.cost_summary["tradeCount"] == 0
    assert all(p["exposurePct"] == 0 for p in result.account_curve)


def test_unknown_missing_day_rejected_instead_of_silent_alignment():
    provider = Provider()
    provider.frames["600000"] = provider.frames["600000"].drop(index=1)
    with pytest.raises(ValueError, match="日期缺口"):
        BacktestEngine(provider, {"rules": Rules()}).run(request())


def test_ten_assets_have_one_capital_and_ten_joint_positions():
    provider = Provider()
    symbols = tuple(str(510300 + i) for i in range(10))
    source = provider.frames["510300"]
    provider.frames = {s: source.copy() for s in symbols}
    provider.list_assets = lambda **kwargs: [Asset(s, s, "etf", "SSE") for s in symbols]
    result = BacktestEngine(provider, {"rules": Rules("hold")}).run(request(symbols=symbols))
    final = result.account_curve[-1]
    assert len(final["positions"]) == 10
    assert final["equity"] == pytest.approx(1000)
    assert final["cashCny"] == pytest.approx(0)
    assert sum(p["weightPct"] for p in final["positions"]) == pytest.approx(100)
    assert all(p["quantity"] == pytest.approx(10) for p in final["positions"])


def test_confirmed_suspension_freezes_account_and_does_not_queue_order():
    provider = Provider()
    missing_day = provider.dates[1]
    provider.frames["510300"] = provider.frames["510300"].drop(index=1)
    provider.nontrading_sessions = lambda symbol, *args: (
        {missing_day.date(): "confirmed"} if symbol == "510300" else {})
    result = BacktestEngine(provider, {"rules": Rules("hold")}).run(request())
    assert not result.trades  # Day-0 buy cannot fill on suspension; no persistent order.
    assert all(p["cashCny"] == 1000 for p in result.account_curve)
    assert result.assumptions["nonTradingExecution"] == "skip_untradable_no_pending_order"


def test_all_suspended_session_has_same_day_only_orders_as_one_suspended_asset():
    class ExitRules(Rules):
        def generate_signals(self, frame, parameters):
            return pd.Series([1, -1, 0, 0] if frame["open"].iloc[0] == 10
                             else [0] * len(frame), dtype=float)

    dates = pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03",
                            "2026-09-04", "2026-09-07"])
    results = []
    for all_suspended in (False, True):
        provider = Provider(count=5)
        for symbol, frame in provider.frames.items():
            frame["date"] = dates
            if symbol == "510300" or all_suspended:
                provider.frames[symbol] = frame.drop(index=2)
        provider.nontrading_sessions = lambda symbol, *args, all_suspended=all_suspended: (
            {date(2026, 9, 3)} if symbol == "510300" or all_suspended else set())
        result = BacktestEngine(provider, {"rules": ExitRules()}).run(request(
            start_date=date(2026, 9, 1), end_date=date(2026, 9, 7)))
        results.append(result)
        assert [(t.trade_date, t.symbol, t.side) for t in result.trades] == [
            (date(2026, 9, 2), "510300", "buy")]
        assert [p["date"] for p in result.account_curve] == [d.date().isoformat() for d in dates]
        suspended = result.account_curve[2]
        assert suspended["equity"] == pytest.approx(1000)
        assert suspended["positions"][0]["quantity"] == pytest.approx(100)
    assert results[0].account_curve == results[1].account_curve


def test_all_assets_unknown_missing_session_is_not_removed_from_account_clock():
    provider = Provider()
    provider.frames = {s: frame.drop(index=1) for s, frame in provider.frames.items()}
    with pytest.raises(ValueError, match="日期缺口"):
        BacktestEngine(provider, {"rules": Rules("hold")}).run(request())


def test_shared_account_rejects_prices_on_non_official_session():
    provider = Provider()
    for frame in provider.frames.values():
        frame.loc[0, "date"] = pd.Timestamp("2026-08-16")  # Sunday.
    with pytest.raises(ValueError, match="非官方交易日"):
        BacktestEngine(provider, {"rules": Rules("hold")}).run(request())


def test_confirmed_all_asset_tail_suspension_keeps_requested_end_valuation():
    provider = Provider()
    provider.frames = {s: frame.drop(index=3) for s, frame in provider.frames.items()}
    provider.nontrading_sessions = lambda *args: {date(2026, 8, 21)}
    result = BacktestEngine(provider, {"rules": Rules("hold")}).run(request())
    assert result.account_curve[-1]["date"] == "2026-08-21"
    assert result.account_curve[-1]["equity"] == result.account_curve[-2]["equity"]
    assert len(result.trades) == 1
    assert len(result.equity_curve) == 4


def test_unknown_all_asset_tail_gap_is_rejected():
    provider = Provider()
    provider.frames = {s: frame.drop(index=3) for s, frame in provider.frames.items()}
    with pytest.raises(ValueError, match="日期缺口"):
        BacktestEngine(provider, {"rules": Rules("hold")}).run(request())


def test_allocation_replays_same_parameters_account_and_costs(monkeypatch):
    monkeypatch.setattr("quant_platform.allocation._today", lambda: date(2026, 8, 24))
    provider = Provider(count=30)
    rules = Rules("hold")
    costs = TradingCosts(0.03, 0.05, 0.02, "asset_date")
    req = request(parameters={"tag": "same"}, trading_costs=costs, cash_pct=10)
    result = BacktestEngine(provider, {"rules": rules}).run(req)
    suggestion = AllocationService(provider, {"rules": rules}).suggest(
        symbols=req.symbols, strategy_id="rules", parameters=req.parameters,
        start_date=req.start_date, cash_pct=10, initial_capital_cny=1000, trading_costs=costs)
    assert suggestion.positions[0].weight_pct == pytest.approx(
        result.account_curve[-1]["positions"][0]["weightPct"])
    assert suggestion.positions[1].weight_pct == 0
    assert suggestion.request["parameters"] == {"tag": "same"}
    assert suggestion.request["tradingCosts"]["stampDutyMode"] == "asset_date"


def test_legacy_diagnostics_preserve_original_execution():
    result = BacktestEngine(Provider(), {"rules": Rules()}).run(request(
        portfolio_mode="legacy_independent", trading_costs=TradingCosts(0.03, 0.05, 0.02)))
    assert len(result.account_curve) == len(result.equity_curve)
    assert [p["equity"] for p in result.account_curve] == pytest.approx(
        result.equity_curve["equity"])
    assert result.trades[0].commission_cny == pytest.approx(500 * 0.0003)
    assert result.cost_summary["tradeCount"] == len(result.trades)
