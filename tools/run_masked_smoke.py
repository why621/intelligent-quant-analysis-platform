"""CR070: use an existing frozen CR069 dataset, never download or publish."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.masked_train import evaluate_research, train_masked


class EqualWeight:
    def predict(self, observation):
        scores = np.zeros(11, dtype=np.float32)
        scores[:10] = observation[:-1].reshape(10, -1)[:, -1]
        return scores, None


def select_mixed(symbols, types, stocks, etfs):
    return ([s for s in symbols if types[s] == "stock"][:stocks]
            + [s for s in symbols if types[s] == "etf"][:etfs])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=256)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; preserve evidence and choose a new directory")
    plan_path = args.experiment / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    types = plan["assetTypes"]
    training = select_mixed(plan["trainingSymbols"], types, 24, 8)
    held_out = select_mixed(plan["heldOutSymbols"], types, 5, 5)
    if set(training) & set(held_out) or len(training) < 10 or len(held_out) != 10:
        raise ValueError("invalid frozen training/holdout separation")
    source = {
        s: pd.read_csv(args.experiment / "data" / f"{s}.csv")
        for s in training + held_out
    }
    costs = TradingCosts(
        commission_pct=0.03, stamp_duty_pct=0.05, slippage_pct=0.02,
        stamp_duty_mode="asset_date",
    )
    network, training_report = train_masked(
        {s: source[s] for s in training}, asset_types=types, splits=plan["splits"],
        destination=args.output / "model", steps=args.steps, max_seconds=180, costs=costs,
    )
    results = []
    groups = [("training_pool_10", select_mixed(training, types, 5, 5))]
    groups += [(f"heldout_{count}", held_out[:count]) for count in (2, 3, 10)]
    for label, symbols in groups:
        for model_name, model in (("masked_sac_smoke", network), ("equal_weight_rebalanced", EqualWeight())):
            result = evaluate_research(
                model, {s: source[s] for s in symbols}, asset_types=types, costs=costs,
                start=plan["splits"]["testStartDate"], end=plan["splits"]["testEndDate"],
                in_sample_end=plan["splits"]["valEndDate"],
            )
            if not all(
                row["cash"] >= 0 and np.isfinite(row["equity"])
                and abs(sum(row["weights"]) + row["cashWeight"] - 1) < 1e-6
                for row in result["curve"]
            ):
                raise AssertionError("invalid shared-account replay")
            result.update({"group": label, "model": model_name})
            results.append(result)
    report = {
        "evidenceKind": "existing_real_data_small_smoke_not_formal_performance_validation",
        "sourcePlanSha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "training": training_report, "heldOutSymbols": held_out, "results": results,
        "newMarketRequests": 0, "productionChanges": 0,
        "limitations": [
            "One seed and bounded smoke budget; no model selection or alpha claims.",
            "CR069 test period previously examined; not a fresh blind test.",
            "Equal weight is rebalanced with identical costs; not the UI no-cost price benchmark.",
            "No within-episode membership changes; no complete EarnMore reproduction.",
        ],
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "steps": training_report["actualSteps"],
        "updates": training_report["optimizerUpdates"],
        "trainingAssets": len(training), "heldoutAssets": len(held_out),
        "results": [{k: row[k] for k in ("group", "model", "totalReturnPct")} for row in results],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
