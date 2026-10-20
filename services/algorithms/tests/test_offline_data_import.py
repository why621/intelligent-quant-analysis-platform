"""Offline replay must not require optional live market-client imports."""

import subprocess
import sys


def test_offline_calendar_does_not_import_live_client():
    code = """
import importlib.abc, sys
from datetime import date
class BlockLive(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'akshare', 'curl_cffi'}:
            raise ImportError('network client forbidden in offline calendar')
sys.meta_path.insert(0, BlockLive())
from quant_platform.data.calendar import sessions
assert sessions(date(2026, 8, 10), date(2026, 8, 11)) == [date(2026, 8, 10), date(2026, 8, 11)]
assert 'quant_platform.data.akshare_provider' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)


def test_existing_provider_exports_keep_identity():
    from quant_platform.data import AkShareMarketDataProvider, UpstreamUnavailableError
    from quant_platform.data import akshare_provider as implementation

    assert AkShareMarketDataProvider is implementation.AkShareMarketDataProvider
    assert UpstreamUnavailableError is implementation.UpstreamUnavailableError
