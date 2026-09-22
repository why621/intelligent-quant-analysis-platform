"""Offline gates for the CR-052 long-window split rules (no torch, no network)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_platform.rl.errors import RLIncompatibleModel, RLInvalidSplit
from quant_platform.rl.splits import (
    Split,
    in_sample_end,
    regime_coverage,
    require_regime_coverage,
    split_from_manifest,
)

LONG_TRAIN = dict(train_start=date(2015, 1, 5), train_end=date(2020, 12, 31))
VAL = dict(val_start=date(2021, 1, 4), val_end=date(2022, 12, 30))


def _prices(closes):
    return pd.DataFrame(
        {
            "date": pd.date_range("2015-01-05", periods=len(closes)),
            "close": closes,
        }
    )


def test_valid_windows_are_recorded_for_the_manifest():
    split = Split(**LONG_TRAIN, **VAL, test_start=date(2023, 1, 3), test_end=date(2025, 6, 30))
    assert split.manifest_fields() == {
        "trainStartDate": "2015-01-05",
        "trainEndDate": "2020-12-31",
        "valStartDate": "2021-01-04",
        "valEndDate": "2022-12-30",
        "testStartDate": "2023-01-03",
        "testEndDate": "2025-06-30",
    }
    assert split.in_sample_end == date(2022, 12, 30)


def test_training_window_must_span_at_least_three_years():
    with pytest.raises(RLInvalidSplit, match="三年"):
        Split(train_start=date(2025, 9, 1), train_end=date(2026, 6, 30))


def test_training_must_start_after_the_verified_history_floor():
    with pytest.raises(RLInvalidSplit, match="2015"):
        Split(train_start=date(2012, 1, 2), train_end=date(2015, 12, 31))


@pytest.mark.parametrize(
    "val",
    [
        pytest.param(dict(val_start=date(2020, 6, 1), val_end=date(2021, 6, 1)),
                     id="overlaps-train"),
        pytest.param(dict(val_start=date(2021, 1, 4)), id="missing-end"),
        pytest.param(dict(val_start=date(2021, 1, 4), val_end=date(2021, 7, 4)),
                     id="shorter-than-one-year"),
        pytest.param(dict(val_start=date(2021, 1, 4), val_end=date(2025, 1, 4)),
                     id="longer-than-two-years"),
    ],
)
def test_validation_window_rules(val):
    with pytest.raises(RLInvalidSplit):
        Split(**LONG_TRAIN, **val)


def test_training_window_without_validation_is_accepted():
    assert Split(**LONG_TRAIN).manifest_fields() == {
        "trainStartDate": "2015-01-05",
        "trainEndDate": "2020-12-31",
    }


def test_reserved_test_window_requires_a_validation_window():
    with pytest.raises(RLInvalidSplit, match="验证"):
        Split(**LONG_TRAIN, test_start=date(2021, 1, 4), test_end=date(2022, 1, 4))
    with pytest.raises(RLInvalidSplit, match="重叠"):
        Split(**LONG_TRAIN, **VAL, test_start=date(2022, 6, 1), test_end=date(2023, 6, 1))


def test_legacy_bundle_stays_usable_but_is_not_a_long_window_split():
    # Weights trained before CR-052 keep their short window and stay loadable,
    # yet they must not be presented as satisfying the three-year requirement.
    legacy = {"trainStartDate": "2025-09-01", "trainEndDate": "2026-06-30"}
    assert in_sample_end(legacy) == "2026-06-30"
    with pytest.raises(RLInvalidSplit, match="三年"):
        split_from_manifest(legacy)


def test_validation_window_counts_as_in_sample():
    manifest = Split(**LONG_TRAIN, **VAL).manifest_fields()
    assert in_sample_end(manifest) == "2022-12-30"
    # Training ends 2020-12-31 but scoring 2021 must still be refused.
    assert in_sample_end({"trainEndDate": "2020-12-31", "valEndDate": "2022-12-30"}) > "2020-12-31"


def test_store_rejects_a_bundle_with_an_impossible_validation_window():
    manifest = {
        "algo": "ppo",
        "seed": 1,
        "featureSignature": "x",
        "publicationDate": "2026-09-18",
        "dataVersion": "y",
        "universeVersion": "z",
        "codeSha": "deadbeef",
        "executionVersion": "account-feedback-v2",
        "trainStartDate": "2015-01-05",
        "trainEndDate": "2020-12-31",
        "valStartDate": "2019-01-01",
        "valEndDate": "2020-01-01",
    }
    from quant_platform.rl.store import validate_manifest

    with pytest.raises(RLIncompatibleModel):
        validate_manifest(manifest)


def test_store_rejects_validation_beyond_the_publication_date():
    manifest = {
        "algo": "ppo",
        "seed": 1,
        "featureSignature": "x",
        "publicationDate": "2022-06-30",
        "dataVersion": "y",
        "universeVersion": "z",
        "codeSha": "deadbeef",
        "executionVersion": "account-feedback-v2",
        "trainStartDate": "2015-01-05",
        "trainEndDate": "2020-12-31",
        "valStartDate": "2021-01-04",
        "valEndDate": "2022-12-30",
    }
    from quant_platform.rl.store import validate_manifest

    with pytest.raises(RLIncompatibleModel, match="publication"):
        validate_manifest(manifest)


def test_regime_coverage_sees_bull_bear_and_sideways():
    import numpy as np

    up = np.linspace(100, 200, 260)
    down = np.linspace(200, 100, 260)
    flat = np.full(120, 100.0)
    prices = _prices(np.concatenate([up, down, flat]))
    coverage = regime_coverage(prices)
    assert coverage["bull"] >= 20 and coverage["bear"] >= 20 and coverage["sideways"] >= 20
    assert require_regime_coverage(prices) == coverage


def test_single_regime_window_is_not_market_coverage():
    import numpy as np

    prices = _prices(np.linspace(100, 400, 600))
    with pytest.raises(RLInvalidSplit, match="bear"):
        require_regime_coverage(prices)


def test_regime_coverage_needs_enough_bars_to_judge():
    with pytest.raises(RLInvalidSplit, match="无法判定"):
        require_regime_coverage(_prices([100.0] * 30))


def test_train_run_rejects_a_short_window_before_importing_torch():
    from quant_platform.rl.train import train_run

    class _Exploding:
        publication_context = {}

        def history(self, *args, **kwargs):
            raise AssertionError("训练区间无效时不得读取行情或开始训练")

    with pytest.raises(RLInvalidSplit, match="三年"):
        train_run(
            publication_root=None,
            models_root=None,
            run_id="ppo-window-gate",
            algo="ppo",
            symbol="510300",
            start=date(2025, 9, 1),
            end=date(2026, 6, 30),
            seed=42,
            total_timesteps=1,
            provider=_Exploding(),
        )


def test_research_history_root_is_marked_as_unpublished_provenance(tmp_path):
    """Weights from a backfill root must never masquerade as a published snapshot."""
    import re
    from types import SimpleNamespace

    from quant_platform.rl.train import _training_provider, _unpublished_context

    provider = _training_provider(None, tmp_path / "research")
    assert not hasattr(provider, "publication_context")

    prices = pd.DataFrame({"date": pd.to_datetime(["2015-01-05", "2026-09-18"])})
    context = _unpublished_context(SimpleNamespace(cache_revision=lambda: "rev-1"), prices)
    assert context["publicationDate"] == "2026-09-18"
    assert re.fullmatch(r"[0-9a-f]{64}", context["dataVersion"])
    assert context["consistency"] == "research_backfill_unpublished"
    assert context["universeVersion"] == "research-backfill-root"

    with pytest.raises(RLInvalidSplit):
        _unpublished_context(provider, pd.DataFrame({"date": []}))
