"""Offline safety checks for the standalone Linux probe; never request live data."""
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tools import check_hs300_sources as probe


def test_total_budget_prevents_network(monkeypatch):
    monkeypatch.setattr(probe, "request_count", probe.MAX_REQUESTS)
    sender = Mock()
    monkeypatch.setattr(probe, "original_request", sender)
    with pytest.raises(RuntimeError, match="budget"):
        probe.bounded_request(Mock(), "GET", "https://example.invalid/")
    sender.assert_not_called()


def test_case_budget_prevents_network(monkeypatch):
    monkeypatch.setattr(probe, "request_count", 0)
    monkeypatch.setattr(probe, "case_requests", 4)
    sender = Mock()
    monkeypatch.setattr(probe, "original_request", sender)
    with pytest.raises(RuntimeError, match="budget"):
        probe.bounded_request(Mock(), "GET", "https://example.invalid/")
    sender.assert_not_called()


def test_request_overrides_timeout_proxy_and_redirects(monkeypatch):
    monkeypatch.setattr(probe, "request_count", 0)
    monkeypatch.setattr(probe, "case_requests", 0)
    monkeypatch.setattr(probe, "last_request", 0)
    response = Mock(status_code=200)
    sender = Mock(return_value=response)
    monkeypatch.setattr(probe, "original_request", sender)
    session = Mock(trust_env=True)
    with patch.object(probe.time, "sleep"):
        probe.bounded_request(session, "GET", "https://example.invalid/", timeout=None)
    assert session.trust_env is False
    assert sender.call_args.kwargs["timeout"] == (5, 8)
    assert sender.call_args.kwargs["allow_redirects"] is False
    assert probe.request_count == probe.case_requests == 1


def test_summary_preserves_missing_values_and_date_flags():
    frame = pd.DataFrame({"date": ["2026-09-07", "2026-09-07"],
                          "close": [10.0, 11.0], "amount": [None, 0]})
    result = probe.summarize(frame)
    assert result["unique_dates"] is False
    assert result["records"][0]["amount"] is None
    assert result["records"][1]["amount"] == 0


def test_empty_summary_rejected():
    with pytest.raises(ValueError, match="empty"):
        probe.summarize(pd.DataFrame())
