"""PPO web gates with synthetic bundles; no dependency load or network."""

import importlib.util
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from quant_platform.rl.errors import RLDependenciesMissing, RLModelNotFound
from quant_platform.rl.policies import PPO
from quant_platform.rl.store import ModelStore
from quant_platform.rl.train import assemble_manifest

from app import create_app
from app.services.errors import ValidationError
from app.services.rl import RLServiceError, validate_web_model
from app.services.strategies import StrategyCatalogService


@pytest.fixture
def configured(tmp_path, monkeypatch):
    original_find = importlib.util.find_spec
    monkeypatch.setattr(
        "app.services.rl.importlib.util.find_spec",
        lambda name: (
            object() if name in {"torch", "gymnasium", "stable_baselines3"} else original_find(name)
        ),
    )
    manifest = assemble_manifest(
        spec=PPO,
        run_id="ppo-test",
        seed=42,
        train_start=date(2025, 9, 9),
        train_end=date(2026, 6, 30),
        publication_context={
            "publicationDate": "2026-09-09",
            "dataVersion": "a" * 64,
            "universeVersion": "test-universe",
        },
        total_timesteps=32,
        code_sha="test",
    )
    store = ModelStore(tmp_path)
    store.save("ppo-test", b"synthetic-model-not-for-inference", manifest)
    saved = store.load("ppo-test")
    release = tmp_path / "release.json"
    release.write_text(
        json.dumps(
            {
                "modelRef": "ppo-test",
                "bundleHash": saved.manifest["bundleHash"],
                "symbols": ["510300"],
                "adjust": "qfq",
            }
        )
    )
    catalog = StrategyCatalogService(rl_release=release)
    dates = pd.bdate_range("2026-07-01", periods=30)
    frame = pd.DataFrame({"date": dates, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0})
    provider = SimpleNamespace(
        publication_context={"universeVersion": "test-universe"}, history=Mock(return_value=frame)
    )
    payload = {
        "strategyId": "ppo",
        "symbols": ["510300"],
        "startDate": "2026-07-01",
        "endDate": "2026-09-09",
        "parameters": {"modelRef": "ppo-test"},
    }
    return catalog, provider, payload, tmp_path, release


def test_catalog_opt_in_and_explicit_experimental_capability(configured):
    catalog, _, _, _, release = configured
    assert len(StrategyCatalogService().list_strategies()["items"]) == 2
    app = create_app({"TESTING": True, "QUANT_RL_RELEASE": str(release)})
    item = app.test_client().get("/api/strategies").json["items"][-1]
    assert item["id"] == "ppo" and item["status"] == "experimental"
    assert item["backtestEnabled"] is True
    assert item["parameterSchema"]["properties"]["modelRef"]["enum"] == ["ppo-test"]
    assert catalog.get_strategy("dqn") is None


def test_unavailable_dependencies_do_not_enable_ppo(configured, monkeypatch):
    *_, release = configured
    monkeypatch.setattr("app.services.rl.importlib.util.find_spec", lambda name: None)
    item = StrategyCatalogService(rl_release=release).list_strategies()["items"][-1]
    assert item["backtestEnabled"] is False


def test_valid_request_records_model_context_without_loading_weights(configured):
    catalog, provider, payload, *_ = configured
    context = validate_web_model(catalog, payload, provider)
    assert context["outOfSampleStartDate"] == "2026-07-01"
    assert context["warmupBars"] == 20 and context["minimumBars"] == 22
    assert catalog.get_strategy("ppo")._model is None


@pytest.mark.parametrize(
    "changes", [{"symbols": ["600519"]}, {"symbols": ["510300", "510500"]}, {"adjust": "none"}]
)
def test_unreviewed_assets_and_adjustment_rejected(configured, changes):
    catalog, provider, payload, *_ = configured
    with pytest.raises(ValidationError):
        validate_web_model(catalog, payload | changes, provider)


def test_training_window_and_short_history_are_typed(configured):
    catalog, provider, payload, *_ = configured
    with pytest.raises(RLServiceError) as error:
        validate_web_model(catalog, payload | {"startDate": "2026-06-30"}, provider)
    assert error.value.code == "RL_IN_SAMPLE_REQUEST"
    provider.history.return_value = provider.history.return_value.iloc[:21]
    with pytest.raises(RLServiceError) as error:
        validate_web_model(catalog, payload, provider)
    assert error.value.code == "RL_INSUFFICIENT_HISTORY"


def test_changed_universe_and_replaced_model_fail_closed(configured):
    catalog, provider, payload, path, _ = configured
    provider.publication_context["universeVersion"] = "different"
    with pytest.raises(RLServiceError) as error:
        validate_web_model(catalog, payload, provider)
    assert error.value.code == "RL_INCOMPATIBLE_MODEL"
    (path / "ppo-test/model.zip").write_bytes(b"replacement")
    with pytest.raises(RLModelNotFound):
        catalog.get_strategy("ppo").create_for_request(payload["parameters"])


def test_arbitrary_reference_rejected_and_errors_do_not_leak_paths(configured):
    catalog, *_ = configured
    with pytest.raises(ValueError):
        catalog.get_strategy("ppo").validate_parameters({"modelRef": "../private"})
    assert "/private" not in RLServiceError(RLDependenciesMissing("/private")).message
