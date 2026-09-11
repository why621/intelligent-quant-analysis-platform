from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError
from quant_platform.data.coverage import assess_history
from quant_platform.data.trading_events import TradingEvent, validate_events
from quant_platform.models import BacktestRequest, TradingCosts

START, END = date(2026, 9, 3), date(2026, 9, 7)


def event(start=START, end=START, reason="suspension"):
    return TradingEvent(
        "stock:SSE:600519",
        start,
        end,
        reason,
        "https://www.sse.com.cn/test-disclosure",
        END,
        "Synthetic test evidence",
    )


def frame(days):
    return pd.DataFrame(
        {
            "date": pd.to_datetime(days),
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 100.0,
            "amount": 1000.0,
        }
    )


def assess(bars, events):
    return assess_history(bars, START, END, events=events, asset_id="stock:SSE:600519")


def test_documented_missing_keeps_market_denominator():
    result = assess(frame(["2026-09-04", "2026-09-07"]), [event()])
    assert result["status"] == "complete_with_exceptions"
    assert result["expectedSessions"] == 3
    assert result["observedSessions"] == result["tradableSessions"] == 2
    assert result["missingSessions"] == ["2026-09-03"]
    assert result["unknownMissingSessions"] == []
    assert result["explainedMissingSessions"][0]["reason"] == "suspension"


def test_unknown_gap_not_promoted_by_unrelated_evidence():
    result = assess(frame(["2026-09-07"]), [event()])
    assert result["status"] == "gaps"
    assert result["unknownMissingSessions"] == ["2026-09-04"]


def test_contradictory_bar_is_invalid():
    result = assess(frame(["2026-09-03", "2026-09-04", "2026-09-07"]), [event()])
    assert result["status"] == "invalid"
    assert result["contradictorySessions"] == ["2026-09-03"]


def test_identity_change_is_classified_but_not_assumed_continuous():
    result = assess(frame(["2026-09-04", "2026-09-07"]), [event(reason="identity_change")])
    assert result["status"] == "gaps"
    assert result["unknownMissingSessions"] == []
    assert result["blockedIdentitySessions"] == ["2026-09-03"]
    assert result["gapReason"] == "identity_change"


def test_prelisting_can_explain_missing_without_creating_prices():
    result = assess(frame(["2026-09-04", "2026-09-07"]), [event(reason="pre_listing")])
    assert result["status"] == "complete_with_exceptions"
    assert result["rowCount"] == 2


def test_overlapping_evidence_rejected():
    with pytest.raises(ValueError, match="overlapping"):
        validate_events([event(), event()])


def test_untrusted_source_rejected():
    with pytest.raises(ValueError, match="official"):
        TradingEvent(
            "stock:SSE:600519",
            START,
            START,
            "suspension",
            "https://sse.com.cn.evil.invalid/test",
            END,
            "test",
        )


def test_provider_accepts_only_explained_gaps_without_fetching(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path, trading_events=[event()])
    bars = frame(["2026-09-04", "2026-09-07"])
    provider._save_history_cache("600519", bars)
    provider._fetch_tencent = Mock(side_effect=AssertionError("network forbidden"))
    with provider.read_only_research(END):
        actual = provider.history("600519", START, END)
        assert len(actual) == 2
        with pytest.raises(UpstreamUnavailableError):
            provider.history("600000", START, END)
    provider._fetch_tencent.assert_not_called()


class BuyStrategy:
    def generate_signals(self, prices, parameters):
        return pd.Series(1.0, index=prices.index)


def test_initial_suspension_keeps_cash_and_never_creates_trade(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path, trading_events=[event()])
    provider._save_history_cache("600519", frame(["2026-09-04", "2026-09-07"]))
    provider._save_history_cache("600000", frame(["2026-09-03", "2026-09-04", "2026-09-07"]))
    result = BacktestEngine(provider, {"test": BuyStrategy()}).run(
        BacktestRequest(
            ("600519", "600000"), "test", START, END, trading_costs=TradingCosts(0, 0, 0)
        )
    )
    assert result.equity_curve["equity"].tolist() == [100000.0, 100000.0, 100000.0]
    suspended_trades = [t for t in result.trades if t.symbol == "600519"]
    assert [t.trade_date for t in suspended_trades] == [END]
    assert result.assumptions["nonTradingValuation"] == "last_observed_close_or_initial_cash"
    assert len(provider._storage.load("600519")) == 2


def test_signal_waits_for_resumption_actual_open(tmp_path):
    middle = date(2026, 9, 4)
    provider = AkShareMarketDataProvider(tmp_path, trading_events=[event(middle, middle)])
    provider._save_history_cache("600519", frame(["2026-09-03", "2026-09-07"]))
    result = BacktestEngine(provider, {"test": BuyStrategy()}).run(
        BacktestRequest(("600519",), "test", START, END, trading_costs=TradingCosts(0, 0, 0))
    )
    assert [t.trade_date for t in result.trades] == [END]
    assert len(result.equity_curve) == 3
    assert len(provider._storage.load("600519")) == 2
