from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from quant_platform.data.publication import load_publication, publish
from tools.daily_publication import consecutive, decision, execute
from tools.test_publication import document

TZ = ZoneInfo("Asia/Shanghai")


def attempt(day, status="succeeded", trigger="scheduled"):
    return {"targetDate": day, "status": status, "trigger": trigger}


def test_only_adjacent_actual_trading_days_count():
    assert consecutive([attempt("2026-09-10"), attempt("2026-09-11")])
    assert consecutive([attempt("2026-09-11"), attempt("2026-09-14")])
    assert not consecutive([attempt("2026-09-10"), attempt("2026-09-14")])
    assert not consecutive([attempt("2026-09-10"), attempt("2026-09-11", trigger="manual")])
    assert not consecutive([attempt("2026-09-10"), attempt("2026-09-11", status="failed")])
    assert not consecutive([attempt("2026-09-10"), attempt("2026-09-10")])


def test_failure_preserves_baseline_and_never_retries_same_day(tmp_path):
    baseline = tmp_path / "baseline"
    initial = document()
    publish(baseline, initial)
    root = tmp_path / "daily"
    now = datetime(2026, 9, 10, 7, 30, tzinfo=TZ)
    calls = []

    def failed(output, target):
        calls.append(target)
        raise ValueError("synthetic source unavailable")

    result = execute(root, now, "scheduled", dry=True, baseline=baseline, build_candidate=failed)
    assert result["decision"] == "eligible" and not root.exists() and not calls
    result = execute(root, now, "scheduled", baseline=baseline, build_candidate=failed)
    assert result["decision"] == "failed"
    assert result["state"]["attempts"][0]["requestUpperBound"] == 1637
    assert load_publication(root / "publication").cache_revision() == initial["publicationId"]
    assert execute(root, now, "scheduled", baseline=baseline, build_candidate=failed)["decision"] == "already_attempted"
    assert len(calls) == 1


def test_budget_and_inflight_are_conservative():
    day = datetime(2026, 9, 14).date()
    baseline = datetime(2026, 9, 7).date()
    state = {"attempts": [attempt("2026-09-08", "running"), attempt("2026-09-09", "failed"), attempt("2026-09-10", "failed"), attempt("2026-09-11", "failed")]}
    assert decision(state, day, baseline) == "budget_exhausted"
    assert decision({"attempts": [attempt("2026-09-14", "running")]}, day, baseline) == "already_attempted"
    with pytest.raises(ValueError):
        execute(None, datetime(2026, 9, 10), "scheduled")


def test_wrong_date_candidate_never_advances_pointer(tmp_path):
    baseline = tmp_path / "baseline"
    initial = document()
    publish(baseline, initial)
    root = tmp_path / "daily"
    result = execute(root, datetime(2026, 9, 10, 7, 30, tzinfo=TZ), "scheduled", baseline=baseline, build_candidate=lambda output, target: initial)
    assert result["decision"] == "failed"
    assert "interval differs" in result["state"]["attempts"][0]["error"]
    assert load_publication(root / "publication").cache_revision() == initial["publicationId"]


def test_index_range_rejected_before_http(monkeypatch):
    from tools.index_probe import probe
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP must not start")
    monkeypatch.setattr("tools.index_probe.requests.get", forbidden)
    for start, end in [("2024-01-01", "2026-09-09"), ("2026-09-09", "2026-09-09"), ("2099-01-01", "2099-09-09")]:
        with pytest.raises(ValueError):
            probe({"start": start, "end": end})
