"""Joint replay errors remain useful 422 responses instead of uncaught runtime errors."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from quant_platform.rl.portfolio_features import insufficient_history

from app.services.allocation import AllocationService
from app.services.rl import RLServiceError
from app.services.strategies import StrategyCatalogService


def test_allocation_maps_short_listed_history_with_symbol(monkeypatch):
    provider = SimpleNamespace(list_assets=lambda **_: [SimpleNamespace(symbol="510300")])

    def reject(**kwargs):
        raise insufficient_history("上市后仅120根行情，未满足140根预热", "510300")

    algorithm = SimpleNamespace(_provider=provider, suggest=reject)
    monkeypatch.setattr("app.services.allocation.research_read", lambda _: nullcontext({}))
    service = AllocationService(algorithm, StrategyCatalogService())
    with pytest.raises(RLServiceError) as error:
        service.suggest(symbols=["510300"], strategy_id="ma_cross", cash_pct=0)
    assert error.value.status == 422
    assert error.value.code == "RL_INSUFFICIENT_HISTORY"
    assert error.value.details["symbol"] == "510300"
    assert "120" in error.value.details["reason"]
    assert "510300" in error.value.message
