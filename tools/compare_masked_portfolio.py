"""Frozen, bounded three-seed research comparison; never promotes a model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.masked_portfolio import VARIANTS
from quant_platform.rl.masked_train import (
    evaluate_research,
    load_research,
    train_masked,
)
from run_masked_smoke import EqualWeight, select_mixed

SEEDS = (42, 137, 2026)
STEPS = 1024


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def metrics(result):
    return {key: value for key, value in result.items() if key != "curve"}


def select_validation(candidates):
    selected = {}
    for variant in VARIANTS:
        available = [row for row in candidates if row["variant"] == variant]
        # Fixed tie-break; never use test observations to choose candidates.
        best = max(available, key=lambda row: (row["validationScore"], -row["seed"]))
        selected[variant] = {"seed": best["seed"], "validationScore": best["validationScore"]}
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve existing evidence; use a new output")
    source = args.experiment / "plan.json"
    plan = json.loads(source.read_text(encoding="utf-8"))
    training = plan["trainingSymbols"]
    heldout = plan["heldOutSymbols"]
    if set(training) & set(heldout):
        raise ValueError("training and heldout overlap")
    types, splits = plan["assetTypes"], plan["splits"]
    validation = plan["validationGroups"]
    if any(not set(group) <= set(training) for group in validation.values()):
        raise ValueError("validation must not expose heldout assets")
    test_groups = {f"seen_{name}": group for name, group in validation.items()}
    test_groups.update({
        "heldout_stocks10": select_mixed(heldout, types, 10, 0),
        "heldout_etfs8": select_mixed(heldout, types, 0, 8),
        "heldout_mixed10": select_mixed(heldout, types, 5, 5),
        "heldout_mixed2": select_mixed(heldout, types, 1, 1),
        "heldout_mixed3": select_mixed(heldout, types, 2, 1),
    })
    args.output.mkdir(parents=True)
    frozen = {
        "sourcePlanSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "variants": list(VARIANTS), "seeds": list(SEEDS), "steps": STEPS,
        "maxSecondsPerCandidate": 180, "trainingSymbols": training,
        "heldoutSymbols": heldout, "splits": splits,
        "validationGroups": validation, "testGroups": test_groups,
        "selection": "mean(validationReturnPct-maxDrawdownPct), tie smaller seed",
        "budget": "equal_environment_steps_and_RL_updates_not_equal_FLOPs",
        "mlp": "same_research_SAC_fixed_slot_encoder_not_CR069_SB3_checkpoint",
        "purpose": "bounded_comparison_not_formal_release", "newMarketRequests": 0,
    }
    write_json(args.output / "frozen-plan.json", frozen)
    plan_hash = hashlib.sha256((args.output / "frozen-plan.json").read_bytes()).hexdigest()
    frames = {symbol: pd.read_csv(args.experiment / "data" / f"{symbol}.csv")
              for symbol in training + heldout}
    costs = TradingCosts(0.03, 0.05, 0.02, stamp_duty_mode="asset_date")

    def evaluate(model, groups, prefix, boundary):
        return [
            {"group": label, **metrics(evaluate_research(
                model, {s: frames[s] for s in symbols}, asset_types=types, costs=costs,
                start=splits[f"{prefix}StartDate"], end=splits[f"{prefix}EndDate"],
                in_sample_end=boundary,
            ))}
            for label, symbols in groups.items()
        ]

    candidates = []
    for variant in VARIANTS:
        for seed in SEEDS:
            key = f"{variant}-{seed}"
            model, report = train_masked(
                {s: frames[s] for s in training}, asset_types=types, splits=splits,
                destination=args.output / key, steps=STEPS, max_seconds=180,
                seed=seed, costs=costs, variant=variant,
            )
            if report["actualSteps"] != STEPS or report["optimizerUpdates"] != STEPS - 31:
                raise RuntimeError("incomplete budget; comparison cannot be called matched")
            rows = evaluate(model, validation, "val", splits["trainEndDate"])
            score = float(np.mean([r["totalReturnPct"] - r["maxDrawdownPct"] for r in rows]))
            candidates.append({
                "variant": variant, "seed": seed, "key": key, "training": report,
                "validation": rows, "validationScore": score,
            })
            write_json(args.output / "validation-progress.json", candidates)
            print(json.dumps({"completed": key, "validationScore": score}), flush=True)
    # Confirm exogenous episode/window sampling matched across all variants.
    for seed in SEEDS:
        sampling = [r["training"]["sampling"] for r in candidates if r["seed"] == seed]
        if any(row != sampling[0] for row in sampling[1:]):
            raise AssertionError("architecture changed the episode sampling")
    selection = {
        "frozenPlanSha256": plan_hash, "testRead": False,
        "selected": select_validation(candidates),
    }
    write_json(args.output / "selection-before-test.json", selection)
    selection_hash = hashlib.sha256((args.output / "selection-before-test.json").read_bytes()).hexdigest()
    tests = []
    for candidate in candidates:
        model, _ = load_research(args.output / candidate["key"])
        tests.append({
            "variant": candidate["variant"], "seed": candidate["seed"],
            "rows": evaluate(model, test_groups, "test", splits["valEndDate"]),
        })
    baseline = evaluate(EqualWeight(), test_groups, "test", splits["valEndDate"])
    summary = {}
    for variant in VARIANTS:
        runs = [r for r in tests if r["variant"] == variant]
        all_rows = [row for run in runs for row in run["rows"]]
        selected = next(r for r in runs if r["seed"] == selection["selected"][variant]["seed"])
        seed_means = [float(np.mean([row["totalReturnPct"] for row in run["rows"]])) for run in runs]
        summary[variant] = {
            "seedMeanReturnsPct": seed_means,
            "meanReturnPct": float(np.mean(seed_means)),
            "seedStdPct": float(np.std(seed_means, ddof=1)),
            "meanMaxDrawdownPct": float(np.mean([r["maxDrawdownPct"] for r in all_rows])),
            "selectedSeed": selected["seed"],
            "selectedMeanReturnPct": float(np.mean([r["totalReturnPct"] for r in selected["rows"]])),
            "meanFees": float(np.mean([r["cumulativeFees"] for r in all_rows])),
            "meanGrossTurnover": float(np.mean([r["grossTurnoverInitialCapital"] for r in all_rows])),
        }
    write_json(args.output / "report.json", {
        "frozenPlanSha256": plan_hash, "selectionBeforeTestSha256": selection_hash,
        "candidates": candidates, "tests": tests, "equalWeight": baseline, "summary": summary,
        "limitations": [
            "Bounded 1024 steps, three seeds, not formal training or evidence of convergence.",
            "Previously examined test period; not a fresh blind test.",
            "Groups overlap; means and seed SD are descriptive, not significance tests.",
            "No full-universe combination enumeration or within-episode membership change.",
        ],
    })
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
