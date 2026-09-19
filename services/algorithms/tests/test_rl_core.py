import numpy as np
import pandas as pd
import pytest

import quant_platform.rl as rl
from quant_platform.rl import features as F
from quant_platform.rl.errors import (
    RLIncompatibleModel,
    RLInSampleRequest,
    RLModelNotFound,
    RLNotTrained,
)
from quant_platform.rl.policies import RL_POLICIES, RLStrategy
from quant_platform.rl.store import ModelStore


def _prices(n=60, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        }
    )


class TestFeatures:
    def test_columns_and_signature(self):
        feats = F.build_features(_prices())
        assert list(feats.columns) == list(F.FEATURE_COLUMNS)
        assert len(F.feature_signature()) == 16

    def test_features_are_causal_no_lookahead(self):
        base = _prices(60)
        clean = F.build_features(base)
        # Perturbing the final bar must not change any earlier feature value.
        shock = base.copy()
        shock.loc[shock.index[-1], "close"] = 999.0
        shocked = F.build_features(shock)
        pd.testing.assert_frame_equal(clean.iloc[:-1], shocked.iloc[:-1])

    def test_expanding_zscore_warmup_is_nan(self):
        arr = F.expanding_zscore(F.build_features(_prices(40)))
        # Nothing is standardisable at the very top; everything is finite once
        # every column has accumulated min_periods finite observations.
        assert np.isnan(arr[0]).all()
        assert np.isnan(arr[: F.MIN_WARMUP - 1]).all()
        assert np.isfinite(arr[-1]).all()

    def test_expanding_normalisation_is_causal(self):
        feats = F.build_features(_prices(40))
        z = F.expanding_zscore(feats)
        shock = feats.copy()
        shock.iloc[-1] = shock.iloc[-1] + 50.0
        z2 = F.expanding_zscore(shock)
        np.testing.assert_allclose(z[:-1], z2[:-1], equal_nan=True)


class TestStore:
    def test_roundtrip_and_content_hash(self, tmp_path):
        store = ModelStore(tmp_path)
        blob = b"PK\x03\x04fake-zip-bytes"
        manifest = {
            "algo": "ppo",
            "seed": 7,
            "featureSignature": F.feature_signature(),
            "publicationDate": "2025-06-30",
            "dataVersion": "deadbeef",
            "universeVersion": "cafe",
            "trainStartDate": "2024-01-01",
            "trainEndDate": "2025-03-31",
            "codeSha": "abc123",
        }
        store.save("run-a1", blob, manifest)
        bundle = store.load("run-a1")
        assert bundle.model_bytes == blob
        assert bundle.manifest["contentHash"]
        assert store.exists("run-a1")

    def test_missing_model_raises(self, tmp_path):
        with pytest.raises(RLModelNotFound):
            ModelStore(tmp_path).load("run-zz")

    def test_tamper_detection(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save(
            "run-a2",
            b"original",
            {
                "algo": "dqn", "seed": 1, "featureSignature": "x", "publicationDate": "d",
                "dataVersion": "v", "universeVersion": "u", "trainStartDate": "s",
                "trainEndDate": "e", "codeSha": "c",
            },
        )
        (tmp_path / "run-a2" / "model.zip").write_bytes(b"tampered!")
        with pytest.raises(RLModelNotFound, match="content hash"):
            store.load("run-a2")

    def test_invalid_run_id_rejected(self, tmp_path):
        with pytest.raises(RLModelNotFound):
            ModelStore(tmp_path).load("../escape")


class TestPolicies:
    def test_metadata_for_all_four(self):
        for sid, spec in RL_POLICIES.items():
            info = RLStrategy(spec).info()
            assert info.strategy_id == sid
            assert info.category == "ai"
            assert info.status == "experimental"
            assert info.requires_trained_model is True
        assert RLStrategy(RL_POLICIES["dqn"]).info().signal_semantics == "discrete_hold"
        for sid in ("ppo", "sac", "ddpg"):
            semantics = RLStrategy(RL_POLICIES[sid]).info().signal_semantics
            assert semantics == "continuous_target_weight"

    def test_validate_parameters(self):
        s = RLStrategy(RL_POLICIES["ppo"])
        s.validate_parameters({"modelRef": "run-1"})
        with pytest.raises(ValueError, match="modelRef"):
            s.validate_parameters({})
        with pytest.raises(ValueError, match="未知参数"):
            s.validate_parameters({"modelRef": "r", "junk": 1})

    def test_untrained_instance_refuses_signals(self):
        s = RLStrategy(RL_POLICIES["sac"])
        with pytest.raises(RLNotTrained):
            s.generate_signals(_prices(30), {"modelRef": "run-x"})

    def test_in_sample_backtest_rejected(self):
        # Inject a bundle + dummy model so we reach the in-sample guard before
        # any gym/torch path is touched.
        s = RLStrategy(RL_POLICIES["ppo"])
        s._bundle = type("B", (), {"manifest": {"trainEndDate": "2025-12-31"}})()
        s._model = object()
        with pytest.raises(RLInSampleRequest):
            s.generate_signals(_prices(40), {"modelRef": "run-y"})

    @staticmethod
    def _manifest(**over):
        base = {
            "algo": "ppo",
            "seed": 1,
            "featureSignature": F.feature_signature(),
            "publicationDate": "2025-06-30",
            "dataVersion": "v",
            "universeVersion": "u",
            "trainStartDate": "2024-01-01",
            "trainEndDate": "2025-03-31",
            "codeSha": "c",
        }
        base.update(over)
        return base

    def test_create_for_request_rejects_wrong_algo_bundle(self, tmp_path):
        # A DQN bundle must never be served to a PPO request.
        store = ModelStore(tmp_path)
        store.save("dqn-run", b"PK\x03\x04x", self._manifest(algo="dqn"))
        ppo = RLStrategy(RL_POLICIES["ppo"], store=store)
        with pytest.raises(RLIncompatibleModel, match="dqn"):
            ppo.create_for_request({"modelRef": "dqn-run"})

    def test_create_for_request_rejects_stale_feature_signature(self, tmp_path):
        store = ModelStore(tmp_path)
        store.save("drift", b"PK\x03\x04x", self._manifest(featureSignature="deadbeef00000000"))
        ppo = RLStrategy(RL_POLICIES["ppo"], store=store)
        with pytest.raises(RLIncompatibleModel, match="签名"):
            ppo.create_for_request({"modelRef": "drift"})

    def test_registry_keys(self):
        reg = rl.registry()
        assert set(reg) == set(RL_POLICIES)
        assert all(rl.is_rl_strategy_id(k) for k in reg)

    def test_models_root_is_gitignored(self):
        # Trained weights must never enter the repo. git check-ignore resolves
        # paths that do not exist, so this touches nothing on disk.
        import subprocess
        from pathlib import Path

        from quant_platform.rl.policies import DEFAULT_MODELS_ROOT

        probe = Path(DEFAULT_MODELS_ROOT) / "run-xyz" / "model.zip"
        out = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(probe)],
            cwd=Path(__file__).resolve().parents[3],
        )
        assert out.returncode == 0, "models/ weights are not gitignored"
