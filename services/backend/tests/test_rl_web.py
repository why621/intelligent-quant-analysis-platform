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
            train_end=date(2026, 6, 30),
            publication_context={
                "publicationDate": "2026-09-09",
                "dataVersion": "a" * 64,
                "universeVersion": "test",
            },
            total_timesteps=32,
            code_sha="test",
        )
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
    assert len(items) == 6
    item = next(x for x in items if x["id"] == algo)
    assert item["status"] == "experimental" and item["backtestEnabled"] is True
    assert item["parameterSchema"]["properties"]["modelRef"]["enum"] == [algo + "-test"]
    strategy = catalog.get_strategy(algo)
    for other in RL_POLICIES:
        if other != algo:
            with pytest.raises(ValueError):
                strategy.validate_parameters({"modelRef": other + "-test"})
    frame = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-07-01", periods=30),
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
        "startDate": "2026-07-01",
        "endDate": "2026-09-09",
    }
    assert validate_web_model(catalog, payload, provider)["modelRef"] == algo + "-test"
    with pytest.raises(RLServiceError) as err:
        validate_web_model(catalog, payload | {"startDate": "2026-06-30"}, provider)
    assert err.value.code == "RL_IN_SAMPLE_REQUEST"
    provider.history.return_value = frame.iloc[:21]
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
