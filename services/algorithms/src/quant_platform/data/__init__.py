"""Market-data provider interfaces."""

from quant_platform.data.akshare_provider import (
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.contracts import MarketDataProvider

__all__ = ["AkShareMarketDataProvider", "MarketDataProvider", "UpstreamUnavailableError"]
