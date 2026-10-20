"""Protocol checks; no market access or training."""

import pytest

pytest.importorskip("torch")

from compare_masked_portfolio import select_validation


def test_selection_uses_validation_only_and_fixed_seed_tie_break():
    candidates = [
        {"variant": variant, "seed": seed, "validationScore": score,
         "testReturn": future}
        for variant in ("mlp", "attention", "masked_attention")
        for seed, score, future in ((42, 1, -99), (137, 1, 99), (2026, 0, 1000))
    ]
    result = select_validation(candidates)
    assert all(row["seed"] == 42 for row in result.values())
    for row in candidates:
        row["testReturn"] *= -100
    assert select_validation(candidates) == result


def test_missing_route_does_not_produce_a_complete_selection():
    with pytest.raises(ValueError):
        select_validation([{"variant": "mlp", "seed": 42, "validationScore": 0}])
