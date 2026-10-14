import copy
import json
from datetime import date, timedelta

import pytest
from quant_platform.data.coverage import digest
from quant_platform.data.publication import PublishedProvider, load_publication, publish

from tools import recover_daily_publication as recovery
from tools import verify_published_provider as gate
from tools.test_partial_publication import partial
from tools.test_publication import document, rehash


@pytest.mark.parametrize("factory", [document, partial])
def test_data_gate_ignores_inherited_model_releases(monkeypatch, factory):
    monkeypatch.setenv("QUANT_RL_RELEASE", "/missing/old-release.json")
    monkeypatch.setenv("QUANT_PORTFOLIO_RELEASE", "/missing/joint-release.json")
    provider = PublishedProvider(factory())
    real_app = gate.create_app

    class AppReady(Exception):
        pass

    def checked_app(*args, **kwargs):
        app = real_app(*args, **kwargs)
        items = app.test_client().get("/api/strategies").json["items"]
        assert {s["id"] for s in items} == {"ma_cross", "momentum_reversal"}
        raise AppReady

    monkeypatch.setattr(gate, "create_app", checked_app)
    with pytest.raises(AppReady):
        gate.verify(provider)
    # Isolation is local to the gate: normal serving still validates its release.
    with pytest.raises(FileNotFoundError):
        real_app({"TESTING": True}, market_data_provider=provider)


def setup_recovery(tmp_path, monkeypatch):
    root, baseline = tmp_path / "daily", tmp_path / "baseline"
    initial = document()
    publish(baseline, initial)
    publish(root / "publication", initial)
    target = date.fromisoformat(initial["endDate"]) + timedelta(days=1)
    original = {"targetDate": target.isoformat(), "status": "failed",
                "errorType": "RLDependenciesMissing", "startedAt": "original",
                "trigger": "scheduled", "requestUpperBound": 1637}
    state = {"mode": "continuous", "attempts": [original]}
    (root / "state.json").write_text(json.dumps(state))
    output = root / target.isoformat()
    for stage in ("stocks", "etfs"):
        (output / stage).mkdir(parents=True)
        manifest = {"startDate": (target - timedelta(days=365)).isoformat(), "endDate": target.isoformat()}
        manifest["candidateId"] = digest(manifest)
        (output / stage / "manifest.json").write_text(json.dumps(manifest))
    candidate = copy.deepcopy(initial)
    candidate["indexWindow"] = {"startDate": initial["startDate"], "endDate": initial["endDate"]}
    candidate.update(schemaVersion=2, startDate=(target-timedelta(days=365)).isoformat(), endDate=target.isoformat())
    rehash(candidate)
    monkeypatch.setattr(recovery, "build_partial", lambda *a: candidate)
    monkeypatch.setattr(recovery, "verify", lambda p: {"passed": True})
    return root, baseline, target, original


def test_offline_recovery_preserves_failure_and_blocks_repeated_recovery(tmp_path, monkeypatch):
    root, baseline, target, original = setup_recovery(tmp_path, monkeypatch)
    result = recovery.recover(root, target, baseline=baseline)
    attempts = json.loads((root / "state.json").read_text())["attempts"]
    assert attempts == [original, result]
    assert result["operation"] == "offline_recovery" and result["requestUpperBound"] == 0
    assert result["trigger"] == "manual" and result["recoveryOf"] == "original"
    assert load_publication(root / "publication").end == target
    with pytest.raises(ValueError, match="latest attempt"):
        recovery.recover(root, target, baseline=baseline)


@pytest.mark.parametrize("failure", ["manifest", "gate", "wrong_day", "wrong_error"])
def test_recovery_rejection_keeps_ledger_and_pointer(tmp_path, monkeypatch, failure):
    root, baseline, target, original = setup_recovery(tmp_path, monkeypatch)
    if failure == "manifest":
        path = root / target.isoformat() / "stocks/manifest.json"
        value = json.loads(path.read_text()); value["candidateId"] = "bad"
        path.write_text(json.dumps(value))
    if failure == "gate":
        def fail(*a):
            raise ValueError("injected gate failure")
        monkeypatch.setattr(recovery, "verify", fail)
    if failure == "wrong_day":
        target += timedelta(days=1)
    if failure == "wrong_error":
        original["errorType"] = "OtherError"
        (root / "state.json").write_text(json.dumps({"mode": "continuous", "attempts": [original]}))
    ledger = (root / "state.json").read_bytes()
    pointer = (root / "publication/current.json").read_bytes()
    with pytest.raises(ValueError):
        recovery.recover(root, target, baseline=baseline)
    assert (root / "state.json").read_bytes() == ledger
    assert (root / "publication/current.json").read_bytes() == pointer
