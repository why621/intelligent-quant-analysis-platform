from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
import requests

from quant_platform.data import market_fetch, upstream
from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError

DAY = date(2026, 9, 4)
STAMP = pd.Timestamp("2026-09-04 15:00", tz="Asia/Shanghai").timestamp()


def row(symbol="600001", **kwargs):
    return {"f12": symbol, "f13": 1, "f3": 10.0, "f6": 10.0, "f124": STAMP, **kwargs}


def test_limits_are_unknown_not_ten_percent_guesses():
    result = market_fetch.summarise([row("300001"), row("688001", f3=-10)], DAY)
    assert result["limitUp"] is None and result["limitDown"] is None
    assert result["advancing"] == 1 and result["declining"] == 1


@pytest.mark.parametrize(
    "pages, message",
    [
        ([{"total": 2, "diff": [row()]}, {"total": 2, "diff": [row()]}], "duplicate"),
        ([{"total": 1, "diff": [row("BK1627")]}], "non-stock"),
        ([{"total": 2, "diff": [row()]}, {"total": 2, "diff": []}], "missing"),
        ([{"total": 2, "diff": [row()]}, {"total": 3, "diff": [row("600002")]}], "changed"),
        ([{"total": 1, "diff": [row(), row("600002")]}], "incomplete"),
    ],
)
def test_bad_pagination_is_never_published(pages, message):
    with (
        patch.object(market_fetch, "_page", side_effect=pages),
        patch.object(market_fetch, "sleep"),
        pytest.raises(ValueError, match=message),
    ):
        market_fetch.fetch_spot(DAY)


def test_valid_pages_cover_declared_total():
    pages = [{"total": 2, "diff": [row()]}, {"total": 2, "diff": [row("600002")]}]
    with (
        patch.object(market_fetch, "_page", side_effect=pages),
        patch.object(market_fetch, "sleep"),
    ):
        result = market_fetch.fetch_spot(DAY)
    assert result["coverage"] == {"total": 2, "priced": 2}
    assert result["turnoverCny"] == 20


@pytest.mark.parametrize(
    "rows",
    [
        [row(f124=None)],
        [row(f124=STAMP + 86400)],
        [row(), row("600002", f124=STAMP - 86400)],
        [row(f3=float("inf"))],
    ],
)
def test_invalid_dates_or_numbers_are_rejected(rows):
    with pytest.raises(ValueError):
        market_fetch.summarise(rows, DAY)


def test_incomplete_turnover_is_null_and_unpriced_rows_are_reported():
    result = market_fetch.summarise([row(), row("600002", f6="-", f3="-")], DAY)
    assert result["turnoverCny"] is None
    assert result["coverage"] == {"total": 2, "priced": 1}


def test_old_northbound_and_old_index_are_not_relabelled():
    old = pd.DataFrame({"日期": ["2024-08-16"], "当日成交净买额": [12.3]})
    index = pd.DataFrame({"date": ["2026-09-02", "2026-09-03"], "close": [10, 11]})
    with patch("akshare.stock_hsgt_hist_em", return_value=old):
        assert market_fetch.fetch_northbound(DAY) is None
    with patch("akshare.stock_zh_index_daily", return_value=index):
        assert market_fetch.fetch_index("000001", "index", DAY) is None


def test_optional_outages_preserve_valid_core(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    core = market_fetch.summarise([row()], DAY)

    def run(stage, payload, **kwargs):
        if stage == "spot":
            return core
        raise RuntimeError("timeout")

    with patch.object(upstream, "run", side_effect=run):
        result = provider.refresh_market_overview()
    assert result["advancing"] == 1
    assert result["indices"] == []
    assert "northboundNetCny" in result["unavailableMetrics"]
    assert provider.market_overview() == result


def test_history_wrapper_bounds_entire_sdk_including_helper(tmp_path):
    provider = AkShareMarketDataProvider(tmp_path)
    with patch.object(upstream, "run", side_effect=RuntimeError("deadline")) as run:
        with pytest.raises(UpstreamUnavailableError):
            provider._fetch_tencent("510300", DAY, DAY, "qfq")
    assert run.call_args.kwargs["timeout"] == 40
    assert run.call_args.args[0] == "history"


def test_page_retry_is_bounded_and_timeout_is_explicit():
    from unittest.mock import Mock

    session = Mock()
    session.get.side_effect = requests.ConnectTimeout()
    with patch.object(market_fetch, "sleep"), pytest.raises(requests.ConnectTimeout):
        market_fetch._page(session, {})
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["timeout"] == (5, 10)
