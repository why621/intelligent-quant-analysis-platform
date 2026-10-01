"""Multi-model release isolation and request gates; synthetic bundles only."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from quant_platform.rl.errors import RLIncompatibleModel, RLModelNotFound
from quant_platform.rl.policies import RL_POLICIES
from quant_platform.rl.store import ModelStore
from quant_platform.rl.train import assemble_manifest

from app.services.rl import RLServiceError, validate_web_model
from app.services.strategies import StrategyCatalogService


@pytest.fixture
def release(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rl.importlib.util.find_spec", lambda name: object())
    store = ModelStore(tmp_path)
    entries = []
    for algo, spec in RL_POLICIES.items():
        ref = algo + "-test"
        manifest = assemble_manifest(
            spec=spec,
            run_id=ref,
            seed=42,
            train_start=date(2025, 9, 9),
            train_end=date(2025, 12, 31),
            publication_context={
                "publicationDate": "2026-09-09",
                "dataVersion": "a" * 64,
                "universeVersion": "test",
            },
            total_timesteps=32,
            code_sha="test",
        )
        manifest["bandPct"] = 0.02
        store.save(ref, b"synthetic-not-for-inference", manifest)
        entries.append(
            {
                "algo": algo,
                "modelRef": ref,
                "bundleHash": store.load(ref).manifest["bundleHash"],
                "symbols": ["510300"],
                "adjust": "qfq",
            }
        )
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"schemaVersion": 2, "models": entries}))
    return path, entries


@pytest.mark.parametrize("algo", list(RL_POLICIES))
def test_each_algorithm_isolated_and_gated(release, algo):
    path, entries = release
    catalog = StrategyCatalogService(rl_release=path)
    items = catalog.list_strategies()["items"]
    assert len(items) == 2 + len(RL_POLICIES)
    item = next(x for x in items if x["id"] == algo)
    assert item["status"] == "experimental" and item["backtestEnabled"] is True
    assert item["modelContext"]["inSampleEndDate"] == "2025-12-31"
    assert "valStartDate" not in item["modelContext"]
    assert "testStartDate" not in item["modelContext"]
    assert item["parameterSchema"]["properties"]["modelRef"]["enum"] == [algo + "-test"]
    strategy = catalog.get_strategy(algo)
    for other in RL_POLICIES:
        if other != algo:
            with pytest.raises(ValueError):
                strategy.validate_parameters({"modelRef": other + "-test"})
    frame = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-01", periods=160),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
        }
    )
    provider = SimpleNamespace(
        publication_context={"universeVersion": "test"}, history=Mock(return_value=frame)
    )
    payload = {
        "strategyId": algo,
        "symbols": ["512100", "600519"],
        "startDate": "2026-01-01",
        "endDate": "2026-09-09",
    }
    assert validate_web_model(catalog, payload, provider)["modelRef"] == algo + "-test"
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload | {"startDate": "2025-12-31"}, provider)
    assert err.value.code == "RL_IN_SAMPLE_REQUEST"
    provider.history.return_value = frame.iloc[:141]
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload, provider)
    assert err.value.details == {"symbol": "512100"}
    provider.history.return_value = frame
    provider.publication_context["universeVersion"] = "changed"
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload, provider)
    assert err.value.code == "RL_INCOMPATIBLE_MODEL"
    (path.parent / (algo + "-test") / "model.zip").write_bytes(b"tampered")
    with pytest.raises(RLModelNotFound):
        strategy.create_for_request({"modelRef": algo + "-test"})


@pytest.mark.parametrize(
    "case",
    ["duplicate", "unknown", "wrong-algo", "wrong-hash", "empty", "version", "extra", "non-object"],
)
def test_bad_release_fails_closed(release, case):
    path, entries = release
    config = {"schemaVersion": 2, "models": entries}
    if case == "duplicate":
        entries[1] = entries[0]
    if case == "unknown":
        entries[0]["algo"] = "other"
    if case == "wrong-algo":
        entries[0]["modelRef"] = entries[1]["modelRef"]
        entries[0]["bundleHash"] = entries[1]["bundleHash"]
    if case == "wrong-hash":
        entries[0]["bundleHash"] = "0" * 64
    if case == "empty":
        config["models"] = []
    if case == "version":
        config["schemaVersion"] = True
    if case == "extra":
        entries[0]["path"] = "private"
    if case == "non-object":
        config = []
    path.write_text(json.dumps(config))
    with pytest.raises((ValueError, RLIncompatibleModel)):
        StrategyCatalogService(rl_release=path)


def test_dependencies_disable_all_models(release, monkeypatch):
    path, _ = release
    monkeypatch.setattr("app.services.rl.importlib.util.find_spec", lambda name: None)
    catalog = StrategyCatalogService(rl_release=path)
    assert all(
        x["backtestEnabled"] is False
        for x in catalog.list_strategies()["items"]
        if x["category"] == "ai"
    )


@pytest.mark.parametrize("algo", list(RL_POLICIES))
def test_ranking_uses_sample_out_warmup_and_own_model(release, algo):
    from quant_platform.rl.errors import RLInSampleRequest, RLInsufficientHistory

    path, _ = release
    strategy = StrategyCatalogService(rl_release=path).get_strategy(algo)
    dates = pd.bdate_range("2026-01-01", "2026-09-18")
    frame = pd.DataFrame({"date": dates, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0})
    provider = SimpleNamespace(
        publication_context={"universeVersion": "test"}, history=Mock(return_value=frame)
    )
    req = strategy.ranking_request(date(2026, 9, 18), "30d", provider)
    assert req.start_date == date(2026, 1, 1)
    assert req.parameters == {"modelRef": algo + "-test"}
    assert req.initial_capital_cny == 100000
    for call in provider.history.call_args_list:
        assert call.args[1] >= date(2026, 1, 1)
    with pytest.raises(RLInSampleRequest):
        strategy.ranking_request(date(2026, 9, 18), "1y", provider)
    # Plenty of bars overall, but insufficient pre-window history must not rank.
    with pytest.raises(RLInsufficientHistory):
        strategy.ranking_request(date(2026, 3, 1), "30d", provider)
    provider.history.return_value = frame.iloc[-141:]
    with pytest.raises(RLServiceError):
        strategy.ranking_request(date(2026, 9, 18), "1d", provider)
    provider.history.return_value = frame.iloc[-142:]
    assert strategy.ranking_request(date(2026, 9, 18), "1d", provider)


def test_validation_cutoff_drives_web_metadata_requests_and_ranking(release):
    from quant_platform.rl.errors import RLInSampleRequest

    path, entries = release
    store = ModelStore(path.parent)
    ref = entries[0]["modelRef"]
    bundle = store.load(ref)
    manifest = dict(bundle.manifest)
    manifest.update(trainStartDate="2015-01-05", trainEndDate="2020-12-31",
                    valStartDate="2021-01-04", valEndDate="2022-12-30")
    # Use a new immutable bundle instead of rewriting an existing model.
    new_ref = "long-window-test"
    manifest["runId"] = new_ref
    store.save(new_ref, b"synthetic-not-for-inference", manifest)
    entries[0]["modelRef"] = new_ref
    entries[0]["bundleHash"] = store.load(new_ref).manifest["bundleHash"]
    path.write_text(json.dumps({"schemaVersion": 2, "models": entries}))
    strategy = StrategyCatalogService(rl_release=path).get_strategy(entries[0]["algo"])
    context = strategy.model_context()
    assert context["outOfSampleStartDate"] == "2022-12-31"
    assert context["inSampleEndDate"] == "2022-12-30"
    assert context["valStartDate"] == "2021-01-04"
    assert context["valEndDate"] == "2022-12-30"
    assert "testStartDate" not in context
    provider = SimpleNamespace(history=Mock(side_effect=AssertionError("must reject first")))
    with pytest.raises(RLInSampleRequest):
        strategy.validate_web_request({"startDate": "2022-12-30",
                                       "endDate": "2023-03-01"}, provider)
    with pytest.raises(RLInSampleRequest):
        strategy.ranking_request(date(2023, 1, 20), "30d", provider)
    provider.history.assert_not_called()


def test_long_model_split_metadata_matches_http_contract(release):
    from pathlib import Path

    import jsonschema
    import yaml

    path, entries = release
    store = ModelStore(path.parent)
    manifest = dict(store.load(entries[0]["modelRef"]).manifest)
    manifest.update(runId="split-contract", trainStartDate="2015-01-05",
                    trainEndDate="2019-12-31", valStartDate="2020-01-02",
                    valEndDate="2021-12-31", testStartDate="2022-01-04",
                    testEndDate="2024-12-31")
    store.save("split-contract", b"synthetic-not-for-inference", manifest)
    entries[0].update(modelRef="split-contract",
                      bundleHash=store.load("split-contract").manifest["bundleHash"])
    path.write_text(json.dumps({"schemaVersion": 2, "models": entries}))
    strategy = StrategyCatalogService(rl_release=path).get_strategy(entries[0]["algo"])
    context = strategy.model_context()
    assert context["testStartDate"] == "2022-01-04"
    assert context["testEndDate"] == "2024-12-31"
    assert context["outOfSampleStartDate"] == "2022-01-01"
    schema_path = Path(__file__).resolve().parents[3] / "packages/contracts/schemas/strategy.yaml"
    schema = yaml.safe_load(schema_path.read_text())["ModelContext"]
    for field in ("symbols", "trainingSymbols"):
        schema["properties"][field]["items"] = {"type": "string", "pattern": "^[0-9]{6}$"}
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    validator.validate(context)


@pytest.fixture
def research_release(release):
    path, entries = release
    store = ModelStore(path.parent)
    selected = []
    for entry in entries:
        if entry["algo"] == "ddpg":
            continue
        manifest = dict(store.load(entry["modelRef"]).manifest)
        ref = entry["algo"] + "-research"
        manifest.update(runId=ref, symbol="510300", trainStartDate="2015-01-05",
                        trainEndDate="2019-12-31", valStartDate="2020-01-02",
                        valEndDate="2021-12-31", testStartDate="2022-01-04",
                        testEndDate="2024-12-31", consistency="research_backfill_unpublished",
                        universeVersion="research-backfill-root")
        store.save(ref, b"synthetic-research-not-for-inference", manifest)
        selected.append({**entry, "modelRef": ref,
                         "bundleHash": store.load(ref).manifest["bundleHash"]})
    config = {"schemaVersion": 3, "targetUniverseVersion": "b" * 64, "models": selected}
    path.write_text(json.dumps(config))
    return path, config


@pytest.mark.parametrize("algo", ["ppo", "dqn", "sac", "td3"])
def test_reviewed_research_release_pins_dates_assets_and_fees(research_release, algo):
    from app.services.errors import ValidationError

    path, config = research_release
    catalog = StrategyCatalogService(rl_release=path)
    frame = pd.DataFrame({"date": pd.bdate_range("2025-01-02", periods=160),
                          "open": 10., "high": 11., "low": 9., "close": 10.})
    provider = SimpleNamespace(publication_context={"universeVersion": "b" * 64},
                               history=Mock(return_value=frame))
    payload = {"strategyId": algo, "symbols": ["510300"], "startDate": "2025-01-02",
               "endDate": "2025-09-01"}
    context = validate_web_model(catalog, payload, provider)
    assert context["universeVersion"] == "research-backfill-root"
    assert context["targetUniverseVersion"] == "b" * 64
    assert context["assetScope"] == "training_symbols"
    assert context["warmupBars"] == 140 and context["minimumBars"] == 142
    assert context["requiredTradingCosts"]["stampDutyPct"] == 0
    assert context["trainingTradingCosts"]["stampDutyPct"] == 0.05
    with pytest.raises(ValidationError):
        validate_web_model(catalog, payload | {"symbols": ["510050"]}, provider)
    with pytest.raises(ValidationError):
        validate_web_model(catalog, payload | {"tradingCosts": {"stampDutyPct": .05}}, provider)
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload | {"startDate": "2021-12-31"}, provider)
    assert err.value.code == "RL_IN_SAMPLE_REQUEST"
    provider.publication_context["universeVersion"] = "c" * 64
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload, provider)
    assert err.value.code == "RL_INCOMPATIBLE_MODEL"
    provider.publication_context["universeVersion"] = "b" * 64
    path.write_text(json.dumps({"schemaVersion": 2, "models": config["models"]}))
    with pytest.raises(RLServiceError):
        validate_web_model(StrategyCatalogService(rl_release=path), payload, provider)


@pytest.mark.parametrize("case", ["bad-target", "extra", "wrong-symbol", "wrong-source"])
def test_research_release_rejects_unreviewed_metadata(research_release, case):
    path, config = research_release
    if case == "bad-target":
        config["targetUniverseVersion"] = "research-backfill-root"
    elif case == "extra":
        config["skipIntegrity"] = True
    else:
        store = ModelStore(path.parent)
        entry = config["models"][0]
        bundle = store.load(entry["modelRef"])
        metadata = {**bundle.manifest, "runId": "wrong-provenance"}
        metadata["symbol" if case == "wrong-symbol" else "consistency"] = "invalid"
        store.save("wrong-provenance", bundle.model_bytes, metadata)
        entry.update(modelRef="wrong-provenance",
                     bundleHash=store.load("wrong-provenance").manifest["bundleHash"])
    path.write_text(json.dumps(config))
    with pytest.raises((ValueError, RLIncompatibleModel)):
        StrategyCatalogService(rl_release=path)
