"""Offline candidate and replay tests use synthetic members and bars."""
import copy
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from quant_platform.data.coverage import digest
from quant_platform.data.storage import OHLCVStore
from quant_platform.data.universe import UniverseSnapshot
from quant_platform.models import Asset

from tools.prepare_history_batch import fetch_one, new_output, prepare_batch

START, END = date(2026, 9, 3), date(2026, 9, 7)


@pytest.fixture
def snapshot():
    return UniverseSnapshot(END, datetime(2026, 9, 8, tzinfo=UTC), "a" * 64,
                            tuple(Asset(str(600000 + n), f"test{n}", "stock", "SSE")
                                  for n in range(300)))


def observation(symbol, start=START, end=END):
    records = pd.DataFrame({"date": ["2026-09-03", "2026-09-04", "2026-09-07"],
                            "open": 10., "high": 12., "low": 9., "close": 11.,
                            "volume": 100., "amount": None}).to_dict("records")
    return {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
            "source": "Tencent", "adjust": "qfq", "sdkVersion": "1.18.94",
            "normalizationVersion": "tx-1.18.94-project-v1",
            "retrievedAt": "2026-09-08T10:00:00+08:00", "error": None,
            "httpTrace": [], "records": records}


def test_whole_denominator_partial_not_published_schema_replay(tmp_path, snapshot):
    manifest = prepare_batch(snapshot, ["600000", "600001"], START, END, tmp_path / "one",
                             fetch=observation, pause=lambda _: None)
    assert manifest["statusCounts"] == {"complete": 2, "not_attempted": 298}
    assert not manifest["priceCoverageComplete"] and not manifest["published"]
    schema = yaml.safe_load((Path(__file__).resolve().parents[1] /
                             "packages/contracts/schemas/coverage.yaml").read_text())
    Draft202012Validator({"$ref": "#/HistoryCandidate", **schema},
                         format_checker=FormatChecker()).validate(manifest)
    replay = prepare_batch(snapshot, ["600000", "600001"], START, END, tmp_path / "two",
                           replay=tmp_path / "one", fetch=Mock(side_effect=AssertionError))
    assert replay["entries"] == manifest["entries"]
    assert replay["networkRequestsThisRun"] == 0
    assert replay["mode"] == "offline_replay"
    assert manifest["candidateId"] == digest({k: v for k, v in manifest.items()
                                             if k != "candidateId"})


def test_incomplete_and_error_not_saved(tmp_path, snapshot):
    def fetch(symbol, *args):
        value = observation(symbol)
        if symbol == "600000":
            value["records"].pop(1)
        else:
            value.update(error="TimeoutExpired", httpTrace=None, records=[])
        return value
    manifest = prepare_batch(snapshot, ["600000", "600001"], START, END, tmp_path / "out",
                             fetch=fetch, pause=lambda _: None)
    assert manifest["statusCounts"] == {"gaps": 1, "source_error": 1, "not_attempted": 298}
    assert not manifest["requestCountExact"]
    assert manifest["requestUpperBoundThisRun"] == 10
    assert OHLCVStore(tmp_path / "out/candidate-cache").revision() == "0"
    assert not OHLCVStore(tmp_path / "out/candidate-cache").has("600000")


def test_replay_tamper_rejected_before_new_output(tmp_path, snapshot):
    prepare_batch(snapshot, ["600000"], START, END, tmp_path / "one",
                  fetch=observation, pause=lambda _: None)
    path = tmp_path / "one/observations/600000.json"
    value = json.loads(path.read_text())
    value["observation"]["records"][0]["close"] = 99
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hash"):
        prepare_batch(snapshot, ["600000"], START, END, tmp_path / "two",
                      replay=tmp_path / "one", fetch=Mock(side_effect=AssertionError))
    assert not (tmp_path / "two").exists()


@pytest.mark.parametrize("symbols", [[], ["600000"] * 2, ["999999"],
                                      [str(600000 + n) for n in range(7)]])
def test_scope_rejected_before_writes(tmp_path, snapshot, symbols):
    fetch = Mock(side_effect=AssertionError)
    with pytest.raises(ValueError):
        prepare_batch(snapshot, symbols, START, END, tmp_path / "out", fetch=fetch)
    assert not (tmp_path / "out").exists()
    fetch.assert_not_called()


def test_output_escape_existing_symlink(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    assert new_output(root / "new", root) == root / "new"
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    for output in [root, tmp_path / "outside", root / "link/outside"]:
        with pytest.raises(ValueError):
            new_output(output, root)


def test_worker_hard_timeout_does_not_claim_zero_requests():
    with patch("tools.prepare_history_batch.subprocess.run",
               side_effect=subprocess.TimeoutExpired("worker", 40)) as run:
        result = fetch_one("600000", START, END)
    assert result["httpTrace"] is None and result["error"] == "TimeoutExpired"
    assert run.call_args.kwargs["timeout"] == 40


def test_mismatched_replay_interval_and_source(tmp_path, snapshot):
    bad = observation("600000")
    bad["source"] = "other"
    def fetch(*args):
        return copy.deepcopy(bad)
    with pytest.raises(ValueError, match="provenance"):
        prepare_batch(snapshot, ["600000"], START, END, tmp_path / "out", fetch=fetch)
    assert not (tmp_path / "out/manifest.json").exists()
