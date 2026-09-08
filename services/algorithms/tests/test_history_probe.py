from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
import requests

from quant_platform.data.akshare_provider import AkShareMarketDataProvider, UpstreamUnavailableError
from quant_platform.data.history_probe import MAX_RESPONSE_BYTES, bounded_requests


def response(status=200, body=b"ok"):
    result = requests.Response()
    result.status_code = status
    result._content = body
    result._content_consumed = True
    return result


def test_actual_calls_bounded_and_settings_restored():
    trace = []
    def fake(session, method, url, **kwargs):
        assert not session.trust_env
        assert kwargs["timeout"] == (5, 10)
        assert kwargs["allow_redirects"] is False and kwargs["stream"] is True
        return response()
    with patch.object(requests.Session, "request", fake):
        with bounded_requests(trace):
            for _ in range(5):
                assert requests.get("https://proxy.finance.qq.com/test").text == "ok"
            with pytest.raises(ValueError, match="budget"):
                requests.get("https://proxy.finance.qq.com/test")
        assert requests.Session.request is fake
    assert len(trace) == 5


@pytest.mark.parametrize("url", ["http://proxy.finance.qq.com/test", "https://example.com",
                                  "https://proxy.finance.qq.com:8443/test",
                                  "https://user:pass@proxy.finance.qq.com/test"])
def test_unapproved_host_protocol_credentials_no_request(url):
    trace = []
    with patch.object(requests.Session, "request") as original, bounded_requests(trace):
        with pytest.raises(ValueError, match="approved"):
            requests.get(url)
        original.assert_not_called()
    assert trace == []


@pytest.mark.parametrize("status,body", [(302, b"redirect"), (403, b"denied"),
                                        (500, b"failed"), (200, b"x" * (MAX_RESPONSE_BYTES + 1))])
def test_status_and_size_fail_without_retry(status, body):
    trace = []
    with (
        patch.object(requests.Session, "request", return_value=response(status, body)) as original,
        bounded_requests(trace), pytest.raises(ValueError),
    ):
        requests.get("https://proxy.finance.qq.com/test")
    assert len(trace) == original.call_count == 1
    assert trace[0]["error"] == "ValueError"


def test_adapter_does_not_deduplicate_conflicting_dates():
    raw = pd.DataFrame({"date": ["2026-09-07"] * 2, "open": [10., 11.],
                        "high": 12., "low": 9., "close": 11., "volume": 100.})
    provider = object.__new__(AkShareMarketDataProvider)
    with (patch("quant_platform.data.akshare_provider.ak.stock_zh_a_hist_tx", return_value=raw),
          pytest.raises(UpstreamUnavailableError, match="duplicate")):
        provider._fetch_tencent_inline("600000", date(2026, 9, 7), date(2026, 9, 7), "qfq")
