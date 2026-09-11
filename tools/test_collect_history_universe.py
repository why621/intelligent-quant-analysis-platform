import json
from unittest.mock import Mock

import pytest

from tools.collect_history_universe import locked, run
from tools.test_prepare_history_batch import (
    END,
    START,
    observation,
)
from tools.test_prepare_history_batch import (
    snapshot as snapshot_fixture,
)


@pytest.fixture
def sample_snapshot():
    return snapshot_fixture.__wrapped__()


def test_budget_and_idempotent_resume(tmp_path, sample_snapshot):
    output = tmp_path / "candidate"
    fetch = Mock(side_effect=observation)
    args = (sample_snapshot, ["600000", "600001", "600002"], START, END, output)
    first = run(*args, request_budget=10, fetch=fetch, pause=lambda _: None)
    assert fetch.call_count == 2
    assert first["statusCounts"] == {"complete": 2, "not_attempted": 298}
    second = run(
        *args, request_budget=10, resume=True, fetch=fetch, pause=lambda _: None
    )
    assert fetch.call_count == 2
    assert first == second
    assert second["requestUpperBoundThisRun"] == 10
    assert not second["published"]


def test_interruption_charged_and_not_automatically_retried(tmp_path, sample_snapshot):
    output = tmp_path / "candidate"
    args = (sample_snapshot, ["600000", "600001"], START, END, output)
    with pytest.raises(KeyboardInterrupt):
        run(*args, fetch=Mock(side_effect=KeyboardInterrupt), pause=lambda _: None)
    fetch = Mock(side_effect=observation)
    result = run(*args, resume=True, fetch=fetch, pause=lambda _: None)
    assert fetch.call_count == 1
    assert fetch.call_args.args[0] == "600001"
    assert result["statusCounts"] == {
        "source_error": 1,
        "complete": 1,
        "not_attempted": 298,
    }
    assert result["requestCountExact"] is False
    assert result["requestUpperBoundThisRun"] == 10
    assert result["chargedSeconds"] >= 41


def test_resume_plan_cannot_silently_expand_budget(tmp_path, sample_snapshot):
    output = tmp_path / "candidate"
    args = (sample_snapshot, ["600000"], START, END, output)
    run(*args, fetch=observation, pause=lambda _: None)
    with pytest.raises(ValueError, match="configuration"):
        run(
            *args,
            resume=True,
            request_budget=1500,
            fetch=Mock(side_effect=AssertionError),
        )


def test_lock_prevents_second_writer(tmp_path):
    with (
        locked(tmp_path),
        pytest.raises(ValueError, match="already running"),
        locked(tmp_path),
    ):
        pass


def test_tampered_observation_rejected_before_resume(tmp_path, sample_snapshot):
    output = tmp_path / "candidate"
    args = (sample_snapshot, ["600000"], START, END, output)
    run(*args, fetch=observation, pause=lambda _: None)
    path = output / "observations/600000.json"
    value = json.loads(path.read_text())
    value["observation"]["records"][0]["close"] = 999
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hash"):
        run(*args, resume=True, fetch=Mock(side_effect=AssertionError))


def test_corrupted_budget_accounting_rejected(tmp_path, sample_snapshot):
    output = tmp_path / "candidate"
    args = (sample_snapshot, ["600000"], START, END, output)
    run(*args, fetch=observation, pause=lambda _: None)
    path = output / "ledger.json"
    value = json.loads(path.read_text())
    value["reservedRequests"] = 0
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="budget"):
        run(*args, resume=True, fetch=Mock(side_effect=AssertionError))


def test_three_failures_stop_batch(tmp_path, sample_snapshot):
    def fail(symbol, start, end):
        value = observation(symbol, start, end)
        return {**value, "error": "synthetic failure", "records": [], "httpTrace": None}

    fetch = Mock(side_effect=fail)
    result = run(
        sample_snapshot,
        [str(600000 + i) for i in range(10)],
        START,
        END,
        tmp_path / "candidate",
        fetch=fetch,
        pause=lambda _: None,
    )
    assert fetch.call_count == 3
    assert result["statusCounts"] == {"source_error": 3, "not_attempted": 297}
    assert result["requestUpperBoundThisRun"] == 15


def test_preflight_failure_creates_no_candidate(tmp_path, sample_snapshot, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        "tools.collect_history_universe.subprocess.run",
        Mock(side_effect=subprocess.CalledProcessError(1, "preflight")),
    )
    with pytest.raises(subprocess.CalledProcessError):
        run(sample_snapshot, ["600000"], START, END, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_seed_reuses_evidence_without_consuming_network_budget(
    tmp_path, sample_snapshot
):
    first = tmp_path / "first"
    run(
        sample_snapshot,
        ["600000"],
        START,
        END,
        first,
        fetch=observation,
        pause=lambda _: None,
    )
    fetch = Mock(side_effect=observation)
    result = run(
        sample_snapshot,
        ["600000", "600001"],
        START,
        END,
        tmp_path / "next",
        seed=first,
        fetch=fetch,
        pause=lambda _: None,
    )
    assert fetch.call_count == 1
    assert fetch.call_args.args[0] == "600001"
    assert result["statusCounts"] == {"complete": 2, "not_attempted": 298}
    assert result["requestUpperBoundThisRun"] == 5
    assert result["seededAssetCount"] == 1


def test_offline_reclassification_explains_only_verified_gap_without_fetch(
    tmp_path, sample_snapshot
):
    from datetime import date

    from quant_platform.data.trading_events import TradingEvent

    def gap(symbol, *args):
        value = observation(symbol)
        value["records"].pop(1)
        return value

    seed = tmp_path / "seed"
    original = run(
        sample_snapshot,
        ["600000", "600001"],
        START,
        END,
        seed,
        fetch=gap,
        pause=lambda _: None,
    )
    event = TradingEvent(
        "stock:SSE:600000",
        date(2026, 9, 4),
        date(2026, 9, 4),
        "suspension",
        "https://www.hkexnews.hk/test.pdf",
        END,
        "synthetic unit fixture explicitly identifying A-share",
    )
    fetch = Mock(side_effect=AssertionError("offline must never fetch"))
    result = run(
        sample_snapshot,
        ["600000", "600001", "600002"],
        START,
        END,
        tmp_path / "reclassified",
        seed=seed,
        events=(event,),
        offline_reclassify=True,
        fetch=fetch,
    )
    fetch.assert_not_called()
    assert result["statusCounts"] == {
        "complete_with_exceptions": 1,
        "gaps": 1,
        "not_attempted": 298,
    }
    assert result["networkRequestsThisRun"] == result["requestUpperBoundThisRun"] == 0
    assert result["mode"] == "offline_replay"
    assert result["seedCandidateId"] == original["candidateId"]
    assert result["eventVersion"] != original["eventVersion"]
    assert not result["priceCoverageComplete"] and not result["published"]
    with pytest.raises(ValueError, match="seed"):
        run(
            sample_snapshot,
            ["600000"],
            START,
            END,
            tmp_path / "bad",
            offline_reclassify=True,
        )
