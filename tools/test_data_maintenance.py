import json
from datetime import date
from types import SimpleNamespace

import pytest
from quant_platform.data.publication import PublishedProvider
from quant_platform.data.trading_events import TradingEvent, load_events
from quant_platform.data.update_results import failure_code

from tools.maintain_trading_events import maintain, merge_confirmed, parse_sse
from tools.test_partial_publication import partial
from tools.test_prepare_history_batch import END, START
from tools.test_publication import document, rehash

ASSETS = {"600000": SimpleNamespace(asset_type="stock", exchange="SSE")}


def official(**changes):
    row = dict(
        productCode="600000",
        controlType="TR",
        type="LXTP",
        stopTime="",
        startStopDate="20260903",
        endStopDate="",
    )
    row.update(changes)
    return {"result": [row], "pageHelp": {"pageNo": 1, "pageCount": 1, "total": 1}}


def event(day=END, reason="suspension"):
    return TradingEvent(
        "stock:SSE:600000",
        day,
        day,
        reason,
        "https://www.sse.com.cn/",
        END,
        "synthetic offline evidence",
    )


def test_continuous_stop_only_confirms_query_day():
    events = parse_sse(
        "callback(" + json.dumps(official()) + ")", END, ASSETS, reviewed_on=date(2026, 9, 8)
    )
    assert events[0].start == events[0].end == END
    assert events[0].reviewed_on == date(2026, 9, 8)
    assert "startStopDate=20260907" in events[0].source_url


@pytest.mark.parametrize(
    "changes",
    [
        {"controlType": "GB"},
        {"type": "LSTP", "stopTime": "AM"},
        {"type": "LSTP", "stopTime": "930"},
        {"type": "LSTP", "stopTime": ""},
    ],
)
def test_conversion_or_intraday_stop_is_not_full_day(changes):
    assert parse_sse(json.dumps(official(**changes)), END, ASSETS) == ()


@pytest.mark.parametrize("kind", ["error", "null", "html", "pages", "count", "old", "future"])
def test_bad_or_unbounded_source_is_rejected(kind):
    value = official()
    if kind == "error":
        value["success"] = "false"
    if kind == "null":
        value["result"] = None
    if kind == "pages":
        value["pageHelp"]["pageCount"] = 2
    if kind == "count":
        value["pageHelp"]["total"] = 2
    if kind == "old":
        value["result"][0]["endStopDate"] = "20260904"
    if kind == "future":
        value["result"][0]["startStopDate"] = "20260908"
    raw = "<html>error</html>" if kind == "html" else json.dumps(value)
    with pytest.raises(ValueError):
        parse_sse(raw, END, ASSETS)


def test_empty_list_does_not_erase_old_evidence_or_extend_it(tmp_path):
    old = event(START)
    report = maintain(
        tmp_path,
        END,
        [old],
        ASSETS,
        getter=lambda _: json.dumps(
            {
                "result": [],
                "pageHelp": {"pageNo": 1, "pageCount": 0, "total": 0},
            }
        ),
    )
    assert load_events(tmp_path / "trading-events.json") == (old,)
    assert report["state"] == "partial"
    assert report["sources"]["SZSE"]["state"] == "pending"


def test_failed_source_preserves_confirmed_history_without_extension(tmp_path):
    def fail(_):
        raise TimeoutError()

    report = maintain(tmp_path, END, [event(START)], ASSETS, getter=fail)
    assert report["state"] == "pending"
    assert load_events(tmp_path / "trading-events.json")[0].end == START


def test_no_capacity_does_not_make_request(tmp_path):
    def forbidden(_):
        raise AssertionError("must not call")

    report = maintain(tmp_path, END, [], ASSETS, request_budget=0, getter=forbidden)
    assert report["requests"] == 0
    assert report["sources"]["SSE"]["reason"] == "request_budget_reserved"


def test_conflicting_identity_evidence_is_not_overwritten():
    old = event(reason="identity_change")
    merged, conflicts = merge_confirmed([old], [event()])
    assert merged == (old,)
    assert conflicts == ["stock:SSE:600000"]


def test_event_merge_is_idempotent_and_keeps_original_provenance():
    old = event()
    assert merge_confirmed([old], [old]) == ((old,), [])


@pytest.mark.parametrize(
    "observation,quality,code",
    [
        ({"httpTrace": [{"status": 429}]}, None, "rate_limited"),
        ({"httpTrace": [{"status": 403}]}, None, "access_denied"),
        ({"httpTrace": [{"status": 502}]}, None, "provider_unavailable"),
        ({"error": "ReadTimeout"}, None, "timeout"),
        ({"error": "SSLError"}, None, "connection_failed"),
        ({"error": "JSONDecodeError"}, None, "invalid_response"),
        ({}, {"status": "invalid"}, "invalid_prices"),
        ({}, {"status": "empty"}, "empty_response"),
        ({}, {"status": "gaps"}, "missing_sessions"),
        ({}, {"status": "complete_with_exceptions"}, "none"),
    ],
)
def test_specific_source_failure_diagnostics(observation, quality, code):
    assert failure_code(observation, quality) == code


def test_resume_uses_actual_bar_and_missing_does_not_extend_suspension():
    value = document()
    value["schemaVersion"] = 2
    value["tradingEvents"] = [event(date(2026, 9, 4)).to_dict()]
    value["histories"]["600000"].pop(1)
    resumed = PublishedProvider(rehash(value))
    assert resumed.availability["assets"]["600000"]["tradingState"] == "resumed"
    value["histories"]["600000"].pop()
    unknown = PublishedProvider(rehash(value))
    assert unknown.availability["assets"]["600000"]["tradingState"] == "unknown"
    assert unknown.availability["assets"]["600000"]["suspended"] is False


def test_update_date_tamper_rejected():
    value = partial()
    value["assetUpdates"] = {
        "600000": {
            "outcome": "retained",
            "reason": "timeout",
            "retryable": True,
            "attempted": True,
            "lastTradeDate": "2026-09-07",
        }
    }
    with pytest.raises(ValueError, match="update evidence"):
        PublishedProvider(rehash(value))


def client(value=None):
    from app import create_app

    return create_app(
        {"TESTING": True}, market_data_provider=PublishedProvider(value or partial())
    ).test_client()


def preflight(c, module="correlation", symbols=None, **extra):
    return c.post(
        "/api/data/capability",
        json={
            "module": module,
            "symbols": symbols or ["600001", "600002"],
            "startDate": START.isoformat(),
            "endDate": END.isoformat(),
            **extra,
        },
    )


def test_module_checks_only_selected_assets_and_optional_benchmark():
    c = client()
    assert preflight(c).json["state"] == "ready"
    assert preflight(c, symbols=["600000", "600001"]).json["state"] == "unavailable"
    assert preflight(c, "backtest", ["600001"]).json["state"] == "ready"
    assert preflight(c, "backtest", ["600001"], benchmark="600000").json["state"] == "unavailable"
    assert c.post("/api/data/capability", json={"module": "overview"}).json["state"] == "partial"


def test_ranking_includes_warmup_not_just_last_row():
    response = client(document()).post(
        "/api/data/capability", json={"module": "ranking", "period": "30d"}
    )
    assert response.json["state"] == "unavailable"
    assert response.json["issues"][0]["symbol"] == "510300"
    assert response.json["issues"][0]["code"] == "DATE_OUT_OF_RANGE"


def test_preflight_revision_is_checked_before_read():
    c = client()
    response = c.post(
        "/api/data/capability",
        json={"module": "overview"},
        headers={"X-Research-Version": "f" * 64},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"module": []},
        {"module": "bad"},
        {"module": "overview", "symbols": []},
        {"module": "allocation", "symbols": ["600000", "600000"]},
        {"module": "ranking", "period": "2y"},
        {
            "module": "correlation",
            "symbols": ["600001", "600002"],
            "startDate": "20260903",
            "endDate": "2026-09-07",
        },
    ],
)
def test_bad_preflight_request_returns_400(payload):
    assert client().post("/api/data/capability", json=payload).status_code == 400


def test_current_suspension_blocks_allocation_without_blocking_history(monkeypatch):
    from quant_platform import allocation

    monkeypatch.setattr(allocation, "_today", lambda: date(2026, 9, 8))
    monkeypatch.setattr(allocation.AllocationService, "_LOOKBACK_DAYS", 4)
    value = partial()
    value["tradingEvents"] = [event().to_dict()]
    c = client(rehash(value))
    result = c.post("/api/data/capability", json={"module": "allocation", "symbols": ["600000"]})
    assert result.status_code == 200
    assert "NO_CURRENT_BAR" in [i["code"] for i in result.json["issues"]]
    assert (
        c.get("/api/assets/600000/history?startDate=2026-09-03&endDate=2026-09-04").status_code
        == 200
    )


def test_worker_malformed_json_object_is_structured_failure(monkeypatch):
    from tools import prepare_history_batch as prepare

    monkeypatch.setattr(prepare.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="[]"))
    result = prepare.fetch_one("600000", START, END)
    prepare.validate_observation(result, "600000", START, END)
    assert result["error"] == "ValueError"
    assert result["records"] == []


def test_new_status_and_preflight_contracts(tmp_path):
    from pathlib import Path

    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    root = Path("packages/contracts/schemas").resolve()
    registry = Registry().with_resources(
        (
            path.as_uri(),
            Resource.from_contents(
                yaml.safe_load(path.read_text()), default_specification=DRAFT202012
            ),
        )
        for path in root.glob("*.yaml")
    )

    def validate(name, payload):
        Draft202012Validator(
            {"$ref": (root / "data.yaml").as_uri() + "#/" + name}, registry=registry
        ).validate(payload)

    value = partial()
    report = maintain(tmp_path, END, [], ASSETS, request_budget=0)
    value["eventMaintenance"] = report
    c = client(rehash(value))
    validate("DataStatus", c.get("/api/data/status").json)
    validate("PublishedCoverage", c.get("/api/data/coverage").json)
    validate("ModuleCapability", preflight(c).json)
    validate("ModuleCapability", preflight(c, symbols=["600000", "600001"]).json)


def test_daily_deadline_is_not_downgraded_to_asset_or_source_failure(tmp_path, monkeypatch):
    from tools import prepare_history_batch as prepare
    from tools.daily_publication import DailyBudgetExceeded

    def deadline(*args, **kwargs):
        raise DailyBudgetExceeded("offline hard deadline")

    with pytest.raises(DailyBudgetExceeded):
        maintain(tmp_path, END, [], ASSETS, getter=deadline)
    monkeypatch.setattr(prepare.subprocess, "run", deadline)
    with pytest.raises(DailyBudgetExceeded):
        prepare.fetch_one("600000", START, END)
