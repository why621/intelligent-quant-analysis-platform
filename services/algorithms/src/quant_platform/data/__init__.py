"""Market-data provider interfaces."""

from quant_platform.data.contracts import MarketDataProvider

__all__ = ["AkShareMarketDataProvider", "MarketDataProvider", "UpstreamUnavailableError"]


def __getattr__(name):
    # Offline calendar/panel consumers must not load a network client stack.
    if name in ("AkShareMarketDataProvider", "UpstreamUnavailableError"):
        from quant_platform.data import akshare_provider

        return getattr(akshare_provider, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
