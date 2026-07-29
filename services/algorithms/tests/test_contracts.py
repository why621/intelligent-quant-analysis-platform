from datetime import date

from quant_platform.backtesting import BacktestRequest
from quant_platform.data import AkShareMarketDataProvider
from quant_platform.models import TradingCosts


def test_backtest_request_accepts_openapi_aligned_contract() -> None:
    request = BacktestRequest(
        symbols=("510300", "510500"),
        strategy_id="ma_cross",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    assert request.symbols == ("510300", "510500")
    assert request.parameters == {}
    assert request.trading_costs == TradingCosts()


def test_akshare_provider_stock_history_returns_dataframe() -> None:
    provider = AkShareMarketDataProvider()
    df = provider.stock_history(
        symbol="510300",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )
    assert df is not None
    for col in ["date", "open", "high", "low", "close", "volume", "amount"]:
        assert col in df.columns
