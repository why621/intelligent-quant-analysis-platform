import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import (
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.storage import DataStatusStore, OHLCVStore


def _frame(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": [1.0] * len(dates),
            "high": [2.0] * len(dates),
            "low": [0.5] * len(dates),
            "close": [1.5] * len(dates),
            "volume": [1000] * len(dates),
            "amount": [1500] * len(dates),
        }
    )


def _tencent_frame(dates: list[str]) -> pd.DataFrame:
    """Match the documented Tencent schema: amount means volume in hands."""
    return pd.DataFrame(
        {
            "date": dates,
            "open": [1.0] * len(dates),
            "close": [1.5] * len(dates),
            "high": [2.0] * len(dates),
            "low": [0.5] * len(dates),
            "amount": [1234] * len(dates),
        }
    )


class TestOHLCVStore:
    def test_save_load_roundtrip(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = _frame(["2025-01-01", "2025-01-02"])
        store.save("510300", frame)

        loaded = store.load("510300")
        assert list(loaded["date"]) == list(frame["date"])
        assert len(loaded) == 2

    def test_save_deduplicates_and_sorts(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = pd.concat(
            [
                _frame(["2025-01-02", "2025-01-03"]),
                _frame(["2025-01-02"]),
            ],
            ignore_index=True,
        )
        store.save("510300", frame)

        loaded = store.load("510300")
        assert len(loaded) == 2
        assert loaded["date"].is_monotonic_increasing

    def test_missing_optional_amount_is_null(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        frame = _frame(["2025-01-01"]).drop(columns="amount")
        store.save("510300", frame)
        assert pd.isna(store.load("510300").iloc[0]["amount"])

    def test_missing_required_column_is_rejected(self, tmp_path: Path):
        store = OHLCVStore(tmp_path)
        with pytest.raises(ValueError, match="missing required"):
            store.save("510300", _frame(["2025-01-01"]).drop(columns="volume"))

    def test_invalid_symbol_is_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="six-digit"):
            OHLCVStore(tmp_path).load("../../secret")

    def test_data_directories_are_isolated(self, tmp_path: Path):
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        OHLCVStore(first_dir).save("510300", _frame(["2025-01-01"]))

        assert not OHLCVStore(second_dir).has("510300")
        assert OHLCVStore(second_dir).load("510300").empty


class TestDataStatusStore:
    def test_initial_status_has_no_update_timestamp(self, tmp_path: Path):
        status = DataStatusStore(tmp_path).load(fallback_asset_count=1)

        assert status.status == "updating"
        assert status.updated_at is None
        assert status.latest_trade_date is None

    def test_status_is_visible_to_another_store_instance(self, tmp_path: Path):
        first = DataStatusStore(tmp_path)
        second = DataStatusStore(tmp_path)

        first.save("ready", date(2025, 1, 3), "complete")
        status = second.load(fallback_asset_count=2)

        assert status.status == "ready"
        assert status.latest_trade_date == date(2025, 1, 3)
        assert status.updated_at is not None
        assert status.message == "complete"

    def test_legacy_status_schema_is_migrated(self, tmp_path: Path):
        database = tmp_path / "market_data.db"
        connection = sqlite3.connect(database)
        connection.execute(
            """
            CREATE TABLE data_status_sync (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                latest_trade_date TEXT,
                message TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO data_status_sync VALUES (1, 'updating', ?, NULL, '初始化状态')",
            ("2025-01-03T09:00:00",),
        )
        connection.commit()
        connection.close()

        status = DataStatusStore(tmp_path).load(fallback_asset_count=1)

        assert status.status == "updating"
        assert status.updated_at is None
        with sqlite3.connect(database) as connection:
            columns = {
                row[1]: row[3]
                for row in connection.execute("PRAGMA table_info(data_status_sync)")
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        assert columns["updated_at"] == 0
        assert version == 2


class TestHistoryCaching:
    @pytest.fixture(autouse=True)
    def inline_sdk_for_cache_unit_tests(self, monkeypatch):
        # Process deadlines have separate tests; here the SDK is mocked in-process.
        monkeypatch.setattr(AkShareMarketDataProvider, "_fetch_tencent",
                            AkShareMarketDataProvider._fetch_tencent_inline)

    def test_cache_hit_does_not_call_network(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._storage.save(
            "510300", _frame(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-06"])
        )

        with patch("akshare.stock_zh_a_hist_tx") as mock_tencent:
            result = provider.history("510300", date(2025, 1, 2), date(2025, 1, 6))
        mock_tencent.assert_not_called()
        assert len(result) == 3

    def test_tencent_volume_is_mapped_to_contract(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with patch(
            "akshare.stock_zh_a_hist_tx",
            return_value=_tencent_frame(["2025-01-02", "2025-01-03"]),
        ):
            result = provider.history("510300", date(2025, 1, 2), date(2025, 1, 3))

        assert result["volume"].tolist() == [1234, 1234]
        assert result["amount"].isna().all()
        assert len(provider._storage.load("510300")) == 2

    def test_network_failure_preserves_but_does_not_serve_partial_cache(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._storage.save("510300", _frame(["2025-01-01", "2025-01-02"]))

        with (
            patch("akshare.stock_zh_a_hist_tx", side_effect=TimeoutError("timeout")),
            pytest.raises(UpstreamUnavailableError),
        ):
            provider.history("510300", date(2025, 1, 1), date(2025, 1, 31))
        assert len(provider._storage.load("510300")) == 2

    def test_network_failure_without_cache_is_explicit(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with (
            patch("akshare.stock_zh_a_hist_tx", side_effect=TimeoutError("timeout")),
            pytest.raises(UpstreamUnavailableError),
        ):
            provider.history("510300", date(2025, 1, 1), date(2025, 1, 31))


class TestDailyUpdate:
    def test_old_cache_and_upstream_failure_is_stale(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}
        provider._storage.save("510300", _frame(["2025-01-02"]))

        with (
            patch.object(provider, "_fetch_tencent", side_effect=UpstreamUnavailableError()),
            patch.object(
                provider, "refresh_market_overview", side_effect=UpstreamUnavailableError()
            ),
        ):
            status = provider.update_daily()

        assert status.status == "stale"
        assert status.latest_trade_date == date(2025, 1, 2)
        assert "available=1/1" in (status.message or "")

    def test_no_cache_and_upstream_failure_is_failed(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}

        with (
            patch.object(provider, "_fetch_tencent", side_effect=UpstreamUnavailableError()),
            patch.object(
                provider, "refresh_market_overview", side_effect=UpstreamUnavailableError()
            ),
        ):
            status = provider.update_daily()
        assert status.status == "failed"

    def test_successful_refresh_is_ready(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        provider._assets = {"510300": provider._assets["510300"]}
        with (
            patch.object(provider, "_fetch_tencent", return_value=_frame(["2025-01-02"])),
            patch("quant_platform.data.akshare_provider._today", return_value=date(2025, 1, 2)),
            patch.object(provider, "refresh_market_overview", return_value={}),
        ):
            status = provider.update_daily()
        assert status.status == "ready"
        assert status.latest_trade_date == date(2025, 1, 2)


class TestMarketOverviewCache:
    def test_cache_hit_avoids_live_api(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        cached = {
            "tradeDate": "2025-01-02",
            "advancing": 1,
            "declining": 2,
            "unchanged": 3,
            "limitUp": 0,
            "limitDown": 0,
            "turnoverCny": 100.0,
            "northboundNetCny": None,
            "indices": [],
        }
        provider._overview_storage.save(cached)

        with patch.object(provider, "_fetch_market_overview") as live:
            assert provider.market_overview() == cached
        live.assert_not_called()

    def test_unavailable_historical_snapshot_is_not_fabricated(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        with pytest.raises(ValueError, match="not available"):
            provider.market_overview(date(2025, 1, 2))

    def test_live_snapshot_uses_last_actual_trade_date(self, tmp_path: Path):
        provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)
        spot = {"tradeDate": "2025-01-03", "advancing": 1, "declining": 1,
                "unchanged": 1, "turnoverCny": 60.0, "limitUp": None, "limitDown": None,
                "indices": [], "northboundNetCny": None}
        from quant_platform.data.market_fetch import fetch_index, fetch_northbound

        def run(stage, payload, **kwargs):
            if stage == "spot":
                return spot
            day = date.fromisoformat(payload["date"])
            return (fetch_northbound(day) if stage == "northbound"
                    else fetch_index(payload["symbol"], payload["name"], day))
        index_frame = pd.DataFrame(
            {
                "date": ["2025-01-02", "2025-01-03"],
                "close": [100.0, 102.0],
            }
        )
        northbound_frame = pd.DataFrame({"日期": ["2025-01-03"], "当日成交净买额": [1.5]})

        with (
            patch("quant_platform.data.upstream.run", side_effect=run),
            patch("akshare.stock_hsgt_hist_em", return_value=northbound_frame),
            patch("akshare.stock_zh_index_daily", return_value=index_frame),
        ):
            result = provider._fetch_market_overview(date(2025, 1, 5))

        assert result["tradeDate"] == "2025-01-03"
        assert result["advancing"] == 1
        assert result["declining"] == 1
        assert result["unchanged"] == 1
        assert result["turnoverCny"] == 60.0
        assert result["indices"][0]["changePct"] == pytest.approx(2.0)
        assert result["northboundNetCny"] == 150_000_000.0


def test_adjusted_price_caches_are_isolated(tmp_path: Path):
    store = OHLCVStore(tmp_path)
    qfq = _frame(["2025-01-02"])
    hfq = qfq.copy()
    hfq["close"] = 9.5
    hfq["high"] = 10.0

    store.save("510300", qfq, adjust="qfq")
    store.save("510300", hfq, adjust="hfq")

    assert store.load("510300", "qfq").iloc[0]["close"] == 1.5
    assert store.load("510300", "hfq").iloc[0]["close"] == 9.5
    assert store.load("510300", "none").empty


def test_legacy_csv_cache_is_migrated_once(tmp_path: Path):
    legacy = _frame(["2025-01-02", "2025-01-03"])
    legacy.to_csv(tmp_path / "510300.csv", index=False)

    store = OHLCVStore(tmp_path)

    assert len(store.load("510300", "qfq")) == 2
    with sqlite3.connect(tmp_path / "market_data.db") as connection:
        marker = connection.execute(
            "SELECT value FROM cache_metadata WHERE key = 'legacy_csv_migrated'"
        ).fetchone()
    assert marker == ("1",)


def test_v1_sqlite_cache_is_migrated_to_qfq(tmp_path: Path):
    database = tmp_path / "market_data.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE ohlcv (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                amount REAL,
                PRIMARY KEY (symbol, trade_date)
            ) WITHOUT ROWID
            """
        )
        connection.execute(
            """
            INSERT INTO ohlcv
                (symbol, trade_date, open, high, low, close, volume, amount)
            VALUES ('510300', '2025-01-02', 1, 2, 0.5, 1.5, 1000, 1500)
            """
        )
        connection.execute("PRAGMA user_version = 1")

    store = OHLCVStore(tmp_path)

    assert len(store.load("510300", "qfq")) == 1
    assert store.load("510300", "hfq").empty
    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2


def test_ready_status_does_not_become_stale_over_weekend(tmp_path: Path):
    store = DataStatusStore(tmp_path)
    store.save("ready", date(2025, 1, 3), "complete")
    with sqlite3.connect(tmp_path / "market_data.db") as connection:
        connection.execute(
            "UPDATE data_status_sync SET updated_at = '2025-01-03T18:00:00'"
        )

    with patch("quant_platform.data.storage._shanghai_today") as mocked_date:
        mocked_date.return_value = date(2025, 1, 5)
        sunday = store.load(fallback_asset_count=1)
        mocked_date.return_value = date(2025, 1, 7)
        tuesday = store.load(fallback_asset_count=1)

    assert sunday.status == "ready"
    assert tuesday.status == "stale"


def test_history_cache_respects_adjust_mode(tmp_path: Path):
    provider = AkShareMarketDataProvider(tmp_path, request_interval_seconds=0)

    def fetch(symbol, start_date, end_date, adjust):
        frame = _frame(["2025-01-02", "2025-01-03"])
        frame["close"] = 1.5 if adjust == "qfq" else 9.5
        frame["high"] = 2.0 if adjust == "qfq" else 10.0
        return frame

    with patch.object(provider, "_fetch_tencent", side_effect=fetch) as mocked_fetch:
        qfq = provider.history(
            "510300", date(2025, 1, 2), date(2025, 1, 3), "qfq"
        )
        hfq = provider.history(
            "510300", date(2025, 1, 2), date(2025, 1, 3), "hfq"
        )

    assert mocked_fetch.call_count == 2
    assert qfq.iloc[-1]["close"] == 1.5
    assert hfq.iloc[-1]["close"] == 9.5
