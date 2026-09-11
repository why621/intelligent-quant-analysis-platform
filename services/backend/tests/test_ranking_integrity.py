from datetime import date
from unittest.mock import patch

import pytest
from quant_platform.models import DataStatus, RankingItem

from app.services.errors import UpstreamUnavailableError
from app.services.ranking import RankingService
from app.services.strategies import StrategyCatalogService


class Provider:
    revision = "1"

    def cache_revision(self):
        return self.revision

    def status(self):
        return DataStatus(status="ready", source="test", asset_count=1,
                          latest_trade_date=date(2026, 9, 7), updated_at=None, message="")


class Algorithm:
    calls = 0

    def rank(self, **kwargs):
        self.calls += 1
        return [RankingItem(rank=1, strategy_id="ma_cross", strategy_name="test",
                            category="traditional", return_pct=1, max_drawdown_pct=1, sharpe=1)]


def test_same_day_correction_invalidates_ranking():
    provider, algorithm = Provider(), Algorithm()
    service = RankingService(algorithm, provider, StrategyCatalogService())
    service.get_ranking("30d")
    service.get_ranking("30d")
    assert algorithm.calls == 1
    provider.revision = "2"
    service.get_ranking("30d")
    assert algorithm.calls == 2


def test_revision_change_during_computation_is_not_cached():
    provider, algorithm = Provider(), Algorithm()
    service = RankingService(algorithm, provider, StrategyCatalogService())
    original = algorithm.rank
    def rank(**kwargs):
        provider.revision = "2"
        return original(**kwargs)
    with patch.object(algorithm, "rank", side_effect=rank):
        with pytest.raises(UpstreamUnavailableError, match="更新"):
            service.get_ranking("30d")
    assert not service._cache
    assert not service._inflight
    assert service.get_ranking("30d")["items"]


def test_single_flight_wait_has_deadline_and_does_not_spawn_duplicate():
    provider, algorithm = Provider(), Algorithm()
    service = RankingService(algorithm, provider, StrategyCatalogService())
    key = (date(2026, 9, 7), "30d", "1")
    service._inflight.add(key)
    with patch("app.services.ranking._RANKING_BUDGET_SECONDS", 0.01):
        with pytest.raises(UpstreamUnavailableError, match="繁忙"):
            service.get_ranking("30d")
    assert algorithm.calls == 0
    assert key in service._inflight


def test_late_computation_result_is_not_published():
    provider, algorithm = Provider(), Algorithm()
    service = RankingService(algorithm, provider, StrategyCatalogService())
    with patch("app.services.ranking._RANKING_BUDGET_SECONDS", 0):
        with pytest.raises(UpstreamUnavailableError, match="超时"):
            service.get_ranking("30d")
    assert not service._cache
    assert not service._inflight


def test_cache_size_is_bounded():
    provider, algorithm = Provider(), Algorithm()
    service = RankingService(algorithm, provider, StrategyCatalogService())
    with patch("app.services.ranking._CACHE_LIMIT", 2):
        for revision in range(5):
            provider.revision = str(revision)
            service.get_ranking("30d")
    assert len(service._cache) == 2
