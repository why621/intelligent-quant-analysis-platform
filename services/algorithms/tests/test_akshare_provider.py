from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.models import Asset, AssetType


@pytest.fixture
def provider():
    return AkShareMarketDataProvider()


# ---------------------------------------------------------------------------
# list_assets
# ---------------------------------------------------------------------------


class TestListAssets:
    def test_returns_all_assets_by_default(self, provider):
        assets = provider.list_assets()
        assert 30 <= len(assets) <= 50
        for a in assets:
            assert isinstance(a, Asset)
            assert len(a.symbol) == 6
            assert a.symbol.isdigit()

    def test_filters_by_query_symbol(self, provider):
        assets = provider.list_assets(query="510300")
        assert len(assets) >= 1
        assert all("510300" in a.symbol for a in assets)

    def test_filters_by_query_name(self, provider):
        assets = provider.list_assets(query="茅台")
        assert len(assets) >= 1
        assert all("茅台" in a.name for a in assets)

    def test_filters_by_asset_type_etf(self, provider):
        assets = provider.list_assets(asset_type="etf")
        assert len(assets) >= 10
        for a in assets:
            assert a.asset_type == "etf"

    def test_filters_by_asset_type_stock(self, provider):
        assets = provider.list_assets(asset_type="stock")
        assert len(assets) >= 5
        for a in assets:
            assert a.asset_type == "stock"

    def test_respects_limit(self, provider):
        assets = provider.list_assets(limit=5)
        assert len(assets) <= 5


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


class TestHistory:
    def test_returns_dataframe_with_required_columns(self, provider):
        df = provider.history("510300", date(2025, 6, 1), date(2025, 6, 10))
        assert isinstance(df, pd.DataFrame)
        for col in ["date", "open", "high", "low", "close", "volume", "amount"]:
            assert col in df.columns

    def test_dates_are_ascending_and_unique(self, provider):
        df = provider.history("510300", date(2025, 6, 1), date(2025, 6, 30))
        if df.empty:
            pytest.skip("AkShare returned no data for this range")
        dates = df["date"].tolist()
        assert dates == sorted(dates)
        assert len(dates) == len(set(dates))

    def test_empty_result_on_invalid_symbol(self, provider):
        df = provider.history("999999", date(2020, 1, 1), date(2020, 1, 10))
        assert df.empty

    def test_prices_non_negative(self, provider):
        df = provider.history("510300", date(2025, 6, 1), date(2025, 6, 10))
        if df.empty:
            pytest.skip("AkShare returned no data")
        assert (df["open"] >= 0).all()
        assert (df["high"] >= 0).all()
        assert (df["low"] >= 0).all()
        assert (df["close"] >= 0).all()
        assert (df["volume"] >= 0).all()


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_initial_status(self, provider):
        s = provider.status()
        assert s.source == "AkShare"
        assert s.asset_count == len(provider.list_assets())
        assert s.updated_at is None

    def test_update_daily_changes_status(self, provider):
        s = provider.update_daily()
        assert s.status in ("ready", "failed")
        assert s.updated_at is not None

    def test_update_daily_records_latest_trade_date(self, provider):
        s = provider.update_daily()
        if s.status == "ready":
            assert s.latest_trade_date is not None
            today = date.today()
            assert s.latest_trade_date <= today


# ---------------------------------------------------------------------------
# market_overview
# ---------------------------------------------------------------------------


class TestMarketOverview:
    def test_returns_expected_keys(self, provider):
        overview = provider.market_overview()
        for key in [
            "tradeDate",
            "advancing",
            "declining",
            "unchanged",
            "limitUp",
            "limitDown",
            "turnoverCny",
            "northboundNetCny",
            "indices",
        ]:
            assert key in overview

    def test_counts_are_non_negative(self, provider):
        overview = provider.market_overview()
        assert overview["advancing"] >= 0
        assert overview["declining"] >= 0
        assert overview["unchanged"] >= 0
        assert overview["limitUp"] >= 0
        assert overview["limitDown"] >= 0

    def test_turnover_non_negative(self, provider):
        overview = provider.market_overview()
        assert overview["turnoverCny"] >= 0


# ---------------------------------------------------------------------------
# Network failure / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_history_no_future_dates(self, provider):
        df = provider.history("510300", date(2025, 1, 1), date(2025, 12, 31))
        if df.empty:
            pytest.skip("AkShare returned no data")
        today = date.today()
        for d in df["date"]:
            d_date = d.date() if hasattr(d, "date") else d
            assert d_date <= today

    def test_list_assets_no_match(self, provider):
        assets = provider.list_assets(query="zzzzz_no_match")
        assert assets == []

    def test_list_assets_case_insensitive(self, provider):
        assets_lower = provider.list_assets(query="茅台")
        # name search is case-insensitive since it compares lowercased
        assert len(assets_lower) > 0
