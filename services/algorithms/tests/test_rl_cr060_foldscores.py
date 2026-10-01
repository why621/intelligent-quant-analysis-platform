"""CR-060 contract: the manifest's per-fold breakdown must describe the model
that ships, not the last evaluation the callback happened to run.

The first real 500k run (25 evaluations) exposed the mismatch: ``foldScores``
carried the step-500000 scores while ``best_model.zip`` — and therefore every
number the grid reports — came from the step-480000 checkpoint. CR-059's
``cr059-check`` could not see it because that run evaluated only once, so the
two meanings coincided.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_platform.rl import grid as G
from quant_platform.rl import selection as S


def _frame(rows=600, seed=3, drift=0.0, start="2015-01-05"):
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0, 0.012, rows) + drift
    close = 100.0 * np.exp(np.cumsum(ret))
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=rows, freq="D"),
            "open": close,
            "high": close * 1.006,
            "low": close * 0.994,
            "close": close,
        }
    )


class Provider:
    """Duck-typed research provider: the trainer only needs history()."""

    publication_context = {
        "publicationDate": "2024-12-31",
        "universeVersion": "cr060-test",
        "dataVersion": "c" * 64,
        "consistency": "synthetic_cr060",
    }

    def __init__(self, master):
        self._master = master

    def cache_revision(self):
        return "cr060-test"

    def history(self, symbol, start, end, adjust="qfq"):
        frame = self._master
        return frame[
            (frame.date >= pd.Timestamp(start)) & (frame.date <= pd.Timestamp(end))
        ].reset_index(drop=True)


def _run(tmp_path, monkeypatch, scripted, **over):
    """Drive the real three-fold pipeline with a scripted score_fold sequence.

    ``score_fold`` is looked up as a module global inside the callback closure,
    so patching ``train.score_fold`` is enough to control every evaluation and
    make "best" land somewhere other than the final one.
    """
    pytest.importorskip("stable_baselines3")
    pytest.importorskip("gymnasium")
    import torch

    from quant_platform.rl import train as T

    torch.set_num_threads(1)
    remaining = list(scripted)

    def fake_score_fold(env, model, metric):
        if not remaining:
            raise AssertionError("score_fold called more often than scripted")
        return remaining.pop(0)

    monkeypatch.setattr(T, "score_fold", fake_score_fold)

    provider = Provider(_frame(rows=3660, seed=21, start="2015-01-01"))
    store = G.ModelStore(tmp_path / "models")
    cfg = G.GridConfig(
        history_root=tmp_path / "history",
        models_root=store.root,
        out_root=tmp_path / "out",
        grid_id="folds060",
        symbols=("synth",),
        algos=("ppo",),
        seeds=(42,),
        train_start=date(2015, 1, 5),
        train_end=date(2018, 6, 30),
        test_start=date(2022, 1, 1),
        test_end=date(2024, 12, 31),
        require_regimes=False,
        **over,
    )
    summary = G.run_grid(cfg, provider=provider, printer=lambda *a, **k: None)
    assert summary["failures"] == []
    return G.ModelStore(store.root).load("ppo-synth-s42").manifest, store


# Four evaluations, three folds each. Best median is the SECOND (5.1); the LAST
# (-1.1) is clearly worse, so the two meanings cannot coincide.
SCRIPTED = [0.5, 0.6, 0.7, 5.0, 5.1, 5.2, 0.1, 0.2, 0.3, -1.0, -1.1, -1.2]


class TestSelectedCheckpointBreakdown:
    def test_manifest_reports_the_selected_checkpoint_not_the_last(self, tmp_path, monkeypatch):
        manifest, store = _run(
            tmp_path, monkeypatch, SCRIPTED, timesteps=2048, eval_freq=512, progress_every=512
        )
        assert manifest["weightSelection"] == "validation-best"
        # The selected statistic is the best MEDIAN seen, i.e. the 2nd eval.
        assert manifest["selectedFoldMedian"] == pytest.approx(5.1)
        assert manifest["bestEvalReward"] == pytest.approx(5.1)
        # ...and the recorded breakdown belongs to that same evaluation: the
        # shipped weight is the best-median checkpoint, so its fold scores ship too.
        assert manifest["foldScores"] == pytest.approx([5.0, 5.1, 5.2])
        assert manifest["foldScores"] != pytest.approx([-1.0, -1.1, -1.2])
        # The invariant CR-059 only satisfied by accident now holds structurally.
        assert manifest["selectedFoldMedian"] == pytest.approx(
            S.median_fold_score(manifest["foldScores"])
        )
        # best_model.zip exists, so "validation-best" is the honest label.
        assert (store.root / "_trainlogs" / "ppo-synth-s42" / "best_model.zip").exists()

    def test_fold_history_keeps_every_evaluation_including_the_last(self, tmp_path, monkeypatch):
        manifest, _ = _run(
            tmp_path, monkeypatch, SCRIPTED, timesteps=2048, eval_freq=512, progress_every=512
        )
        history = manifest["foldHistory"]
        assert len(history) == 4  # one entry per evaluation, not just the last
        for entry in history:
            assert entry["median"] == pytest.approx(S.median_fold_score(entry["foldScores"]))
        assert [entry["timesteps"] for entry in history] == [512, 1024, 1536, 2048]
        # The final evaluation is still recorded — it is just not what ships.
        assert history[-1]["foldScores"] == pytest.approx([-1.0, -1.1, -1.2])

    def test_the_evaluation_curve_is_untouched(self, tmp_path, monkeypatch):
        _, store = _run(
            tmp_path, monkeypatch, SCRIPTED, timesteps=2048, eval_freq=512, progress_every=512
        )
        with np.load(store.root / "_trainlogs" / "ppo-synth-s42" / "evaluations.npz") as data:
            assert data["fold_scores"].shape == (4, 3)
            assert list(data["timesteps"]) == [512, 1024, 1536, 2048]


class TestNoEvaluationFallback:
    def test_a_run_too_short_to_evaluate_reports_no_fold_scores(self, tmp_path, monkeypatch):
        """Without best_model.zip the shipped weight is the final one; there is
        no breakdown to report, and saying so beats inventing one."""
        manifest, _ = _run(
            tmp_path,
            monkeypatch,
            SCRIPTED,
            timesteps=2048,
            eval_freq=100_000,  # never fires
            progress_every=2048,
        )
        assert manifest["weightSelection"] == "final"
        assert "selectedFoldMedian" not in manifest
        assert manifest["foldScores"] == []
        assert manifest["foldHistory"] == []