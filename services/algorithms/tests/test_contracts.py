from datetime import date

import pytest

from quant_platform.backtesting import BacktestRequest
from quant_platform.data import AkShareMarketDataProvider


def test_backtest_request_accepts_valid_contract() -> None:
    request = BacktestRequest(
        assets=("000001", "600000"),
        strategy="ma_crossover",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert request.assets == ("000001", "600000")
    assert request.params == {}


def test_backtest_request_rejects_invalid_date_range() -> None:
    with pytest.raises(ValueError, match="start_date"):
        BacktestRequest(
            assets=("000001",),
            strategy="ma_crossover",
            start_date=date(2025, 12, 31),
            end_date=date(2025, 1, 1),
        )


def test_akshare_provider_is_an_explicit_implementation_slot() -> None:
    provider = AkShareMarketDataProvider()

    with pytest.raises(NotImplementedError, match="stock_zh_a_hist"):
        provider.stock_history(
            symbol="000001",
            start_date="20250101",
            end_date="20251231",
        )
