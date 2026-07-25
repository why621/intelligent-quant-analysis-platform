"""Compatibility export for the application-wide market data protocol."""

from quant_platform.interfaces import MarketDataProvider
from quant_platform.models import AdjustMode, Asset, AssetType, DataStatus

__all__ = [
    "AdjustMode",
    "Asset",
    "AssetType",
    "DataStatus",
    "MarketDataProvider",
]
