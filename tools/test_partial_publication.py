import copy

import pytest
from quant_platform.data.akshare_provider import UpstreamUnavailableError
from quant_platform.data.publication import PublishedProvider, publish, load_publication
from tools.test_publication import document, rehash
from tools.test_prepare_history_batch import START, END


def partial(symbol="600000", missing=-1):
    value = document()
    value["schemaVersion"] = 2
    value["histories"][symbol].pop(missing)
    return rehash(value)


def test_asset_gap_does_not_block_healthy_history_or_overview():
    provider = PublishedProvider(partial())
    assert len(provider.history("600001", START, END)) == 3
    assert len(provider.history("600000", START, END.replace(day=4))) == 2
    with pytest.raises(UpstreamUnavailableError):
        provider.history("600000", START, END)
    assert provider.availability["readyCount"] == 326
    assert provider.availability["assets"]["600000"]["lastTradeDate"] == "2026-09-04"
    overview = provider.market_overview()
    assert overview["coverage"]["priced"] == 299
    assert overview["unavailable"] == 1
    assert overview["suspended"] == 0
    assert overview["partial"] is True
    assert overview["turnoverCny"] is None


def test_internal_gap_cannot_be_hidden_by_latest_row():
    provider = PublishedProvider(partial(missing=1))
    assert provider.availability["assets"]["600000"]["state"] == "partial"
    with pytest.raises(UpstreamUnavailableError):
        provider.history("600000", START, END)
    assert len(provider.history("600000", END, END)) == 1


def test_empty_asset_does_not_block_etf():
    value = partial()
    value["histories"]["600000"] = []
    provider = PublishedProvider(rehash(value))
    assert provider.availability["assets"]["600000"]["state"] == "unavailable"
    assert len(provider.history("510300", START, END)) == 3


@pytest.mark.parametrize("failure", ["hash", "price", "directory"])
def test_invalid_partial_snapshot_preserves_current(tmp_path, failure):
    good = partial()
    publish(tmp_path, good)
    bad = copy.deepcopy(good)
    if failure == "directory":
        bad["histories"].pop("600001")
    else:
        bad["histories"]["600001"][0]["close"] = -1
    if failure != "hash":
        rehash(bad)
    with pytest.raises(ValueError):
        publish(tmp_path, bad)
    assert load_publication(tmp_path).cache_revision() == good["publicationId"]


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_old_index_does_not_block_stock_history(missing):
    value = partial()
    if missing:
        value["indexRaw"] = None
    else:
        value["indexWindow"] = {"startDate": START.isoformat(), "endDate": "2026-09-04"}
    provider = PublishedProvider(rehash(value))
    assert len(provider.history("600001", START, END)) == 3
    assert provider.market_overview()["indices"] == []
    with pytest.raises(UpstreamUnavailableError):
        provider.history("index:CSI:000300", START, END)


def test_partial_api_exposes_truthful_coverage():
    from app import create_app

    provider = PublishedProvider(partial())
    client = create_app({"TESTING": True}, market_data_provider=provider).test_client()
    status = client.get("/api/data/status")
    assert status.status_code == 200
    assert status.json["availability"]["complete"] is False
    overview = client.get("/api/market/overview")
    assert overview.status_code == 200
    assert overview.json["unavailable"] == 1
    coverage = client.get("/api/data/coverage")
    assert coverage.status_code == 200
    assert coverage.json["dataContext"] == overview.json["dataContext"]


def test_partial_never_counts_as_complete_automatic_day():
    from tools.daily_publication import consecutive

    assert not consecutive(
        [
            {"targetDate": "2026-09-10", "status": "succeeded", "trigger": "scheduled"},
            {"targetDate": "2026-09-11", "status": "partial", "trigger": "scheduled"},
        ]
    )


def test_stock_failure_still_runs_etfs_and_index(tmp_path, monkeypatch):
    import tools.daily_publication as daily
    from tools.test_prepare_history_batch import snapshot

    publish(tmp_path / "baseline", document())
    monkeypatch.setattr(daily, "BASE", tmp_path / "baseline")
    monkeypatch.setattr(daily, "load_snapshot", lambda _: snapshot.__wrapped__())
    monkeypatch.setattr(daily, "load_events", lambda _: ())
    calls = []

    def fail(*args, **kwargs):
        calls.append("stocks")
        raise ValueError("source failed")

    monkeypatch.setattr(daily, "run", fail)
    monkeypatch.setattr(daily, "collect", lambda *a, **k: calls.append("etfs"))
    monkeypatch.setattr(daily, "collect_index", lambda *a, **k: calls.append("index"))
    monkeypatch.setattr(daily, "build_partial", lambda *a, **k: partial())
    monkeypatch.setattr(daily, "verify", lambda _: {"partial": True})
    out = tmp_path / "out"
    out.mkdir()
    daily.pipeline(out, END)
    assert calls == ["stocks", "etfs", "index"]


@pytest.mark.parametrize(
    "symbol,stage_name", [("600001", "stocks"), ("510300", "etfs")]
)
def test_builder_falls_back_individually_without_splicing(
    tmp_path, monkeypatch, symbol, stage_name
):
    import json
    import tools.build_partial_publication as builder
    from quant_platform.data.coverage import digest
    from quant_platform.data.index_snapshot import save_index
    from tools.test_prepare_history_batch import snapshot, observation

    latest = document()
    old = copy.deepcopy(latest)
    old["endDate"] = "2026-09-04"
    for rows in old["histories"].values():
        rows.pop()
    rehash(old)
    monkeypatch.setattr(builder, "load_snapshot", lambda _: snapshot.__wrapped__())
    events = tmp_path / "events.json"
    events.write_text("[]")
    stage = tmp_path / stage_name
    (stage / "observations").mkdir(parents=True)
    obs = observation(symbol)
    wrapper = {"observation": obs, "sha256": digest(obs)}
    (stage / "observations" / (symbol + ".json")).write_text(json.dumps(wrapper))
    manifest = {
        "startDate": START.isoformat(),
        "endDate": END.isoformat(),
        "universeVersion": latest["universe"]["snapshotId"],
        "entries": [{"symbol": symbol, "observationSha256": digest(obs)}],
    }
    manifest["candidateId"] = digest(manifest)
    (stage / "manifest.json").write_text(json.dumps(manifest))
    save_index(latest["indexRaw"].encode("utf-8"), START, END, tmp_path / "index")
    result = builder.build_partial(tmp_path, START, END, old, tmp_path, events)
    provider = PublishedProvider(result)
    assert len(provider.history(symbol, START, END)) == 3
    assert result["histories"]["600000"] == old["histories"]["600000"]
    assert provider.availability["affectedCount"] == 326
    with pytest.raises(UpstreamUnavailableError):
        provider.history("600000", START, END)


def test_confirmed_suspension_is_not_unknown_missing_or_synthetic_price():
    value = partial()
    value["tradingEvents"] = [
        {
            "asset_id": "stock:SSE:600000",
            "start": END.isoformat(),
            "end": END.isoformat(),
            "reason": "suspension",
            "reviewed_on": END.isoformat(),
            "source_url": "https://static.cninfo.com.cn/finalpage/test.PDF",
            "evidence_note": "Synthetic reviewed suspension fixture",
        }
    ]
    provider = PublishedProvider(rehash(value))
    assert len(provider.history("600000", START, END)) == 2
    assert provider.availability["assets"]["600000"]["suspended"] is True
    assert provider.market_overview()["suspended"] == 1
    assert provider.market_overview()["unavailable"] == 0


def test_no_new_valid_data_never_advances(tmp_path, monkeypatch):
    import tools.build_partial_publication as builder
    from tools.test_prepare_history_batch import snapshot

    monkeypatch.setattr(builder, "load_snapshot", lambda _: snapshot.__wrapped__())
    events = tmp_path / "events.json"
    events.write_text("[]")
    with pytest.raises(ValueError, match="no independently validated"):
        builder.build_partial(tmp_path, START, END, document(), tmp_path, events)


def test_partial_history_api_checks_requested_interval():
    from app import create_app

    client = create_app(
        {"TESTING": True}, market_data_provider=PublishedProvider(partial())
    ).test_client()
    prefix = "/api/assets/"
    query = f"?startDate={START}&endDate={END}"
    assert client.get(prefix + "600001/history" + query).status_code == 200
    assert client.get(prefix + "600000/history" + query).status_code == 503
    assert (
        client.get(
            prefix + "600000/history?startDate=2026-09-03&endDate=2026-09-04"
        ).status_code
        == 200
    )


def test_interrupted_etf_stage_keeps_verified_completed_entries(tmp_path):
    import json
    from tools.collect_etf_candidate import collect
    from tools.test_prepare_history_batch import observation
    from quant_platform.data.coverage import digest

    calls = []

    def fetch(symbol, start, end):
        calls.append(symbol)
        if len(calls) == 2:
            raise ValueError("synthetic worker interruption")
        return observation(symbol)

    with pytest.raises(ValueError):
        collect(tmp_path / "etfs", START, END, fetch=fetch, pause=lambda _: None)
    manifest = json.loads((tmp_path / "etfs/manifest.json").read_text())
    assert manifest["candidateId"] == digest(
        {k: v for k, v in manifest.items() if k != "candidateId"}
    )
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["asset"]["symbol"] == calls[0]


def test_cloud_probe_accepts_partial_but_rejects_inconsistent_breadth(monkeypatch):
    import json
    from app import create_app
    import tools.run_cloud_daily as cloud

    provider = PublishedProvider(partial())
    client = create_app({"TESTING": True}, market_data_provider=provider).test_client()
    response = {
        "status": client.get("/api/data/status").json,
        "overview": client.get("/api/market/overview").json,
    }
    monkeypatch.setattr(cloud, "command", lambda *a, **k: json.dumps(response))
    cloud.probe(provider.cache_revision(), END.isoformat())
    response["overview"]["unchanged"] += 1
    with pytest.raises(ValueError, match="breadth"):
        cloud.probe(provider.cache_revision(), END.isoformat())


def test_partial_status_contract():
    import yaml
    from pathlib import Path
    from jsonschema import Draft202012Validator, FormatChecker

    schema = yaml.safe_load(Path("packages/contracts/schemas/data.yaml").read_text())
    Draft202012Validator(
        {"$ref": "#/PublicationAvailability", **schema}, format_checker=FormatChecker()
    ).validate(PublishedProvider(partial()).availability)


def test_manual_live_release_is_preferred_over_older_daily_candidate(
    tmp_path, monkeypatch
):
    import tools.daily_publication as daily
    from datetime import datetime
    from zoneinfo import ZoneInfo

    daily_root = tmp_path / "daily"
    live = tmp_path / "live"
    publish(daily_root / "publication", document())
    newer = partial()
    newer["endDate"] = "2026-09-08"
    newer["indexWindow"] = {"startDate": START.isoformat(), "endDate": END.isoformat()}
    publish(live, rehash(newer))
    selected = []

    def pipeline(output, target, source):
        selected.append(source)
        raise ValueError("stop after source selection")

    monkeypatch.setattr(daily, "pipeline", pipeline)
    result = daily.execute(
        daily_root,
        datetime(2026, 9, 10, 7, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        "scheduled",
        baseline=live,
        build_candidate=pipeline,
    )
    assert result["decision"] == "failed"
    assert selected == [live]
