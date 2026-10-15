"""Value-only benchmarks use real provider history semantics on suspended windows.

These unit fixtures call PublishedProvider.history/nontrading_sessions unchanged;
they do not constitute a validated publication or external suspension evidence.
"""

from datetime import date

import pandas as pd
import pytest

from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.akshare_provider import UpstreamUnavailableError
from quant_platform.data.publication import PublishedProvider
from quant_platform.data.trading_events import TradingEvent
from quant_platform.models import Asset, BacktestRequest


def fixture_provider(*, missing_last_evidence=False, no_prior=False):
    provider = object.__new__(PublishedProvider)
    provider.start, provider.end = date(2026, 10, 9), date(2026, 10, 14)
    provider._assets = {
        "601059": Asset("601059", "unit stock", "stock", "SSE"),
        "510300": Asset("510300", "unit ETF", "etf", "SSE"),
    }
    dates = pd.to_datetime(["2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14"])
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [10, 10, 11, 12],
            "high": [10, 10, 11, 12],
            "low": [10, 10, 11, 12],
            "close": [10, 10, 11, 12],
            "volume": [1000] * 4,
        }
    )
    provider._frames = {"601059": frame.iloc[: 0 if no_prior else 1].copy(), "510300": frame}
    provider.trading_events = (
        TradingEvent(
            asset_id="stock:SSE:601059",
            start=date(2026, 10, 12),
            end=date(2026, 10, 13) if missing_last_evidence else date(2026, 10, 14),
            reason="pre_listing" if no_prior else "suspension",
            reviewed_on=date(2026, 10, 14),
            source_url="https://www.sse.com.cn/unit-test-fixture",
            evidence_note="Explicit synthetic fixture; not external verification",
        ),
    )
    return provider


def benchmark(provider):
    request = BacktestRequest(
        ("601059", "510300"),
        "ma_cross",
        start_date=date(2026, 10, 13),
        end_date=date(2026, 10, 14),
        benchmark_mode="buy_and_hold",
    )
    return BacktestEngine(provider, {})._benchmark_curve(
        request,
        pd.to_datetime(["2026-10-13", "2026-10-14"]),
    )


def test_published_reader_whole_window_suspension_has_real_value_anchor():
    provider = fixture_provider()
    before = provider._frames["601059"].copy(deep=True)
    with pytest.raises(UpstreamUnavailableError, match="no tradable history"):
        provider.history("601059", date(2026, 10, 13), date(2026, 10, 14))
    curve = benchmark(provider)
    assert curve.tolist() == pytest.approx([1, (1 + 12 / 11) / 2])
    pd.testing.assert_frame_equal(provider._frames["601059"], before)
    assert len(provider._frames["601059"]) == 1  # No synthetic suspended OHLC added.


def test_whole_window_with_one_unknown_gap_is_not_valued_as_suspension():
    with pytest.raises(UpstreamUnavailableError, match="unexplained gaps"):
        benchmark(fixture_provider(missing_last_evidence=True))


def test_whole_prelisting_window_without_real_prior_price_stays_rejected():
    with pytest.raises(UpstreamUnavailableError, match="no tradable history"):
        benchmark(fixture_provider(no_prior=True))
