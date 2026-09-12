import json
import subprocess
import sys
from datetime import date, timedelta
from time import monotonic
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform import cli
from quant_platform.data import market_fetch, overview_worker, upstream
from quant_platform.data.akshare_provider import (
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.storage import DataStatusStore


@pytest.fixture
def provider(tmp_path):
    value = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
    value._assets = {"510300": value._assets["510300"]}
    return value


@pytest.fixture
def snapshot():
    return {
        "tradeDate": "2026-09-04",
        "advancing": 1,
        "declining": 2,
        "unchanged": 3,
        "limitUp": 0,
        "limitDown": 0,
        "turnoverCny": None,
        "northboundNetCny": None,
        "indices": [],
    }


def test_cold_http_read_never_calls_upstream(provider):
    with patch.object(provider, "_fetch_overview_bounded") as fetch:
        with pytest.raises(UpstreamUnavailableError, match="unavailable"):
            provider.market_overview()
    fetch.assert_not_called()


def test_failed_refresh_retains_snapshot(provider, snapshot):
    provider._overview_storage.save(snapshot)
    with patch.object(provider, "_fetch_overview_bounded", side_effect=UpstreamUnavailableError):
        with pytest.raises(UpstreamUnavailableError):
            provider.refresh_market_overview()
    assert provider.market_overview() == snapshot


def test_retry_then_success(provider, snapshot):
    success = subprocess.CompletedProcess([], 0, json.dumps(snapshot), "")
    failure = subprocess.CalledProcessError(1, [], stderr="ConnectionError: upstream")
    with (
        patch(
            "quant_platform.data.upstream.subprocess.run", side_effect=[failure, success]
        ) as run,
        patch("quant_platform.data.upstream.sleep") as sleep,
    ):
        assert upstream.run("spot", {"date": "2026-09-04"}, timeout=180, attempts=2) == snapshot
    assert run.call_count == 2
    assert run.call_args.kwargs["timeout"] == 180
    sleep.assert_called_once_with(1)
    assert provider._overview_storage.load() is None


def test_real_hung_process_is_killed_and_retries_are_bounded(provider):
    real_run = subprocess.run

    def hung_worker(*args, **kwargs):
        return real_run([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    started = monotonic()
    with (
        patch(
            "quant_platform.data.upstream.subprocess.run", side_effect=hung_worker
        ) as run,
        patch("quant_platform.data.akshare_provider._OVERVIEW_TIMEOUT_SECONDS", 0.1),
        patch("quant_platform.data.akshare_provider.sleep"),
        pytest.raises(UpstreamUnavailableError),
    ):
        provider.refresh_market_overview()
    assert run.call_count == 1
    assert monotonic() - started < 5
    assert provider._overview_storage.load() is None


def test_worker_stdout_is_json_only(snapshot, monkeypatch, capsys):
    def fetch(day):
        print("upstream progress")
        assert day == date(2026, 9, 4)
        return snapshot

    monkeypatch.setattr(sys, "argv", ["worker", "2026-09-04"])
    monkeypatch.setattr(AkShareMarketDataProvider, "_fetch_market_overview", fetch)
    overview_worker.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == snapshot
    assert "upstream progress" in captured.err


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("today, bar_day, history_state", [
    (date(2026, 9, 11), date(2026, 9, 11), "ready"),
    (date(2026, 9, 12), date(2026, 9, 11), "ready"),
    (date(2026, 9, 13), date(2026, 9, 11), "ready"),
    (date(2026, 9, 12), date(2026, 9, 10), "stale"),
])
def test_overview_failure_does_not_mark_history_failed(
    provider, snapshot, cached, today, bar_day, history_state
):
    if cached:
        provider._overview_storage.save(snapshot)
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp(bar_day)],
            "open": [1],
            "high": [2],
            "low": [1],
            "close": [2],
            "volume": [100],
        }
    )
    with (
        patch("quant_platform.data.akshare_provider._today", return_value=today),
        patch.object(provider, "_fetch_tencent", return_value=frame),
        patch.object(provider, "refresh_market_overview", side_effect=UpstreamUnavailableError),
    ):
        status = provider.update_daily()
    assert status.status == "stale"
    assert status.components["history"]["status"] == history_state
    assert status.latest_trade_date == bar_day
    assert status.components["history"]["failedSymbols"] == ([] if history_state == "ready" else ["510300"])
    assert status.components["overview"]["status"] == ("stale" if cached else "failed")
    assert DataStatusStore(provider._storage.data_dir).load(1).components == status.components
    assert status.updated_at.utcoffset() == timedelta(hours=8)
    with patch("quant_platform.cli.AkShareMarketDataProvider", return_value=provider):
        with patch.object(provider, "update_daily", return_value=status):
            assert cli.main() == 2  # Do not hide degraded data from automation.


def test_history_errors_record_symbol_and_traceback(provider, caplog):
    with (
        patch.object(provider, "_fetch_tencent", side_effect=RuntimeError("network down")),
        patch.object(provider, "refresh_market_overview", return_value={}),
    ):
        status = provider.update_daily()
    assert status.components["history"]["failedSymbols"] == ["510300"]
    assert status.components["history"]["status"] == "failed"
    assert status.components["overview"]["status"] == "ready"
    assert "network down" in caplog.text


def test_missing_turnover_is_null_and_date_is_not_fabricated(provider):
    timestamp = pd.Timestamp("2026-09-04 15:00", tz="Asia/Shanghai").timestamp()
    rows = [{"f3": 1, "f6": None, "f124": timestamp}]
    result = market_fetch.summarise(rows, date(2026, 9, 6))
    assert result["turnoverCny"] is None
    assert result["tradeDate"] == "2026-09-04"
    with pytest.raises(ValueError, match="verified trade date"):
        market_fetch.summarise([{"f3": 1}], date(2026, 9, 6))
