"""Deterministic RL training-pipeline smoke test (requires the ``[rl]`` extra).

This exercises the *real* ``train_run`` -> ``ModelStore`` -> ``RLStrategy``
inference path end to end. The price frame is **synthetic and fixed-seed** and is
used purely as a pipeline-correctness harness — it is NOT a research
publication, NOT real market data, and asserts NO profitability or risk metric.
Ladder step 3 (bit-identical inference), not step 4 (real-snapshot training).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")
pytestmark = pytest.mark.rl

from quant_platform.rl import features  # noqa: E402
from quant_platform.rl.policies import RL_POLICIES, RLStrategy  # noqa: E402
from quant_platform.rl.store import ModelStore  # noqa: E402
from quant_platform.rl.train import train_run  # noqa: E402


def _synthetic_ohlc(*, first_day: date, rows: int, seed: int) -> pd.DataFrame:
    """Fixed-seed random-walk OHLC — deterministic so the run is reproducible."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0002, 0.01, size=rows)
    close = 100.0 * np.cumprod(1.0 + rets)
    open_ = np.empty(rows)
    open_[0] = close[0] * (1 + rets[0] * 0.1)
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.004, size=rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.004, size=rows))
    dates = pd.date_range(first_day, periods=rows, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1e6,
            "amount": close * 1e6,
        }
    )


def _provider(frame: pd.DataFrame, publication_date: date):
    context = {
        "publicationDate": publication_date.isoformat(),
        "universeVersion": "smoke-universe",
        "dataVersion": "a" * 64,
        "consistency": "synthetic_pipeline_smoke",
    }
    return SimpleNamespace(
        history=lambda symbol, start, end, adjust="qfq": frame,
        publication_context=context,
    )


def test_train_save_load_infer_pipeline_is_deterministic(tmp_path):
    train_start = date(2023, 1, 2)
    rows = 220
    frame = _synthetic_ohlc(first_day=train_start, rows=rows, seed=7)
    train_end = (train_start + timedelta(days=rows - 1))

    models_root = tmp_path / "models"
    run_id = "ppo-smoke-0001"
    model_dir = train_run(
        publication_root=tmp_path / "unused",
        models_root=models_root,
        run_id=run_id,
        algo="ppo",
        symbol="SYNTH",
        start=train_start,
        end=train_end,
        seed=42,
        total_timesteps=512,
        provider=_provider(frame, train_end),
    )
    assert (model_dir / "model.zip").exists()
    assert (model_dir / "manifest.json").exists()

    manifest = ModelStore(models_root).load(run_id).manifest
    assert manifest["algo"] == "ppo"
    assert manifest["featureSignature"] == features.feature_signature()
    assert manifest["trainEndDate"] == train_end.isoformat()
    assert manifest["consistency"] == "synthetic_pipeline_smoke"

    # Inference on an OUT-OF-SAMPLE slice (first date strictly after trainEndDate).
    oos = _synthetic_ohlc(
        first_day=train_end + timedelta(days=1), rows=60, seed=11
    )
    shared = RLStrategy(RL_POLICIES["ppo"], store=ModelStore(models_root))

    def _signals():
        instance = shared.create_for_request({"modelRef": run_id})
        return instance.generate_signals(oos, {})

    first = _signals()
    second = _signals()
    assert len(first) == len(oos)
    np.testing.assert_array_equal(first.to_numpy(), second.to_numpy())

    # Same instance, called twice -> identical output (guards recurrent-state
    # leakage that a fresh-load-each-time check would miss).
    inst = shared.create_for_request({"modelRef": run_id})
    np.testing.assert_array_equal(
        inst.generate_signals(oos, {}).to_numpy(),
        inst.generate_signals(oos, {}).to_numpy(),
    )

    finite = first.dropna().to_numpy()
    assert finite.size > 0
    assert np.all((finite >= 0.0) & (finite <= 1.0))


def test_inference_rejects_in_sample_window(tmp_path):
    train_start = date(2023, 1, 2)
    rows = 180
    frame = _synthetic_ohlc(first_day=train_start, rows=rows, seed=5)
    train_end = train_start + timedelta(days=rows - 1)
    models_root = tmp_path / "models"
    train_run(
        publication_root=tmp_path / "unused",
        models_root=models_root,
        run_id="ppo-smoke-0002",
        algo="ppo",
        symbol="SYNTH",
        start=train_start,
        end=train_end,
        seed=42,
        total_timesteps=256,
        provider=_provider(frame, train_end),
    )
    from quant_platform.rl.errors import RLInSampleRequest

    shared = RLStrategy(RL_POLICIES["ppo"], store=ModelStore(models_root))
    instance = shared.create_for_request({"modelRef": "ppo-smoke-0002"})
    with pytest.raises(RLInSampleRequest):
        # Starts inside the training window -> must be refused.
        instance.generate_signals(frame, {})
