"""Offline HTTP safety checks; never download a real file."""
import json
import sys
from unittest.mock import MagicMock

import pytest

from tools import prepare_universe_snapshot as tool


def sender(monkeypatch, *, status=200, chunks=(b"abc",)):
    response = MagicMock(status_code=status)
    response.__enter__.return_value = response
    response.iter_content.return_value = iter(chunks)
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = response
    monkeypatch.setattr(tool.requests, "Session", lambda: session)
    return session


def test_one_direct_bounded_request(monkeypatch):
    session = sender(monkeypatch)
    assert tool.download_source() == b"abc"
    session.get.assert_called_once_with(
        tool.SOURCE_URL, timeout=(5, 10), allow_redirects=False, stream=True)
    assert session.trust_env is False


@pytest.mark.parametrize("status", [302, 403, 500])
def test_no_redirect_or_retry(monkeypatch, status):
    session = sender(monkeypatch, status=status)
    with pytest.raises(ValueError, match="HTTP"):
        tool.download_source()
    session.get.assert_called_once()


def test_response_size_limit(monkeypatch):
    sender(monkeypatch, chunks=(b"x" * (tool.MAX_SOURCE_BYTES + 1),))
    with pytest.raises(ValueError, match="oversized"):
        tool.download_source()


def test_hard_deadline():
    with pytest.raises(TimeoutError, match="45 seconds"):
        tool._deadline(None, None)


@pytest.mark.parametrize("existing", [False, True])
def test_output_scope_checked_before_download(tmp_path, monkeypatch, existing):
    root = tmp_path / "repo"
    monkeypatch.setattr(tool, "__file__", str(root / "tools/tool.py"))
    output = root / "artifacts/existing" if existing else tmp_path / "outside"
    if existing:
        output.mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["prepare", "--output", str(output)])
    fetch = MagicMock()
    monkeypatch.setattr(tool, "download_source", fetch)
    with pytest.raises(SystemExit):
        tool.main()
    fetch.assert_not_called()


def test_tampered_replay_has_no_http_or_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    monkeypatch.setattr(tool, "__file__", str(root / "tools/tool.py"))
    captured = root / "artifacts/captured"
    captured.mkdir(parents=True)
    (captured / "source.xls").write_bytes(b"changed")
    (captured / "download.json").write_text(json.dumps({
        "sourceUrl": tool.SOURCE_URL, "sourceSha256": "0" * 64,
        "retrievedAt": "2026-09-08T18:00:00+08:00",
    }))
    output = root / "artifacts/output"
    monkeypatch.setattr(sys, "argv", [
        "prepare", "--output", str(output), "--input-download", str(captured)])
    fetch = MagicMock()
    monkeypatch.setattr(tool, "download_source", fetch)
    with pytest.raises(ValueError, match="provenance"):
        tool.main()
    fetch.assert_not_called()
    assert not output.exists()
