"""Independent release-evidence guardrails, using explicit synthetic unit fixtures."""

from copy import deepcopy
from datetime import date

import pandas as pd
import pytest

from tools.evaluate_universe_candidates import assert_ledger


def ledger_fixture():
    frames = {
        "stock": pd.DataFrame(
            {"date": ["2026-08-10", "2026-08-11"], "close": [100.0, 100.0]}
        ),
        "etf": pd.DataFrame(
            {"date": ["2026-08-10", "2026-08-11"], "close": [10.0, 10.0]}
        ),
    }
    initial = {
        "date": "2026-08-10",
        "symbols": ["stock", "etf"],
        "cash": 100000.0,
        "quantities": [0.0, 0.0],
        "equity": 100000.0,
        "weights": [0.0, 0.0],
        "cashWeight": 1.0,
    }
    filled = {
        "date": "2026-08-11",
        "symbols": ["stock", "etf"],
        "cash": 98999.0,
        "quantities": [10.0, 0.0],
        "equity": 99999.0,
        "weights": [1000 / 99999, 0.0],
        "cashWeight": 98999 / 99999,
        "fills": [
            {
                "symbol": "stock",
                "side": "buy",
                "quantity": 10.0,
                "amount_cny": 1000.0,
                "commission_cny": 1.0,
                "stamp_duty_cny": 0.0,
            }
        ],
    }
    return {"symbols": ["stock", "etf"], "accountCurve": [initial, filled]}, frames


def test_release_evidence_recomputes_actual_cash_and_holdings():
    result, frames = ledger_fixture()
    assert_ledger(result, frames, {})
    for field in ("cash", "equity"):
        corrupt = deepcopy(result)
        corrupt["accountCurve"][1][field] += 2
        with pytest.raises(AssertionError):
            assert_ledger(corrupt, frames, {})
    corrupt = deepcopy(result)
    corrupt["accountCurve"][1]["fills"][0]["commission_cny"] = 0
    with pytest.raises(AssertionError):
        assert_ledger(corrupt, frames, {})


def test_release_evidence_rejects_fills_on_verified_suspension():
    result, frames = ledger_fixture()
    with pytest.raises(AssertionError, match="nontrading"):
        assert_ledger(result, frames, {"stock": {date(2026, 8, 11)}})


def test_release_evidence_rejects_fabricated_quantity_or_weights():
    result, frames = ledger_fixture()
    for field, value in (
        ("quantities", [20.0, 0.0]),
        ("weights", [0.0, 0.0]),
        ("weights", [0.0, 1000 / 99999]),
    ):
        corrupt = deepcopy(result)
        corrupt["accountCurve"][1][field] = value
        with pytest.raises(AssertionError):
            assert_ledger(corrupt, frames, {})


def test_resume_rejects_changed_frozen_training_identity():
    from tools.train_universe_candidates import validate_candidate

    plan = {
        "splits": {"trainStartDate": "2025-09-09", "trainEndDate": "2026-07-10"},
        "stepsPerCandidate": 65536,
        "maxSecondsPerCandidate": 1200,
        "trainingSymbols": ["stock", "etf"],
    }
    hashes = {"stock": "a" * 64, "etf": "b" * 64}
    manifest = {
        "purpose": "formal_candidate",
        "algo": "ppo",
        "seed": 42,
        "splits": plan["splits"],
        "dataHashes": hashes,
        "requestedTimesteps": 65536,
        "maxSeconds": 1200,
        "trainingUniverse": ["stock", "etf"],
        "tradingCosts": {
            "commissionPct": 0.03,
            "slippagePct": 0.02,
            "stampDutyPct": 0.05,
            "stampDutyMode": "asset_date",
        },
    }
    validate_candidate(manifest, plan, hashes, "ppo", 42)
    for field, value in (
        ("seed", 137),
        ("dataHashes", {"stock": "c" * 64, "etf": "b" * 64}),
        ("splits", {**plan["splits"], "trainEndDate": "2026-08-07"}),
        ("tradingCosts", {**manifest["tradingCosts"], "commissionPct": 0.08}),
    ):
        corrupt = deepcopy(manifest)
        corrupt[field] = value
        with pytest.raises(ValueError, match="frozen"):
            validate_candidate(corrupt, plan, hashes, "ppo", 42)
