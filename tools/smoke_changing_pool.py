"""Bounded real-data switching smoke; training partition only, no performance selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.masked_train import train_masked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a new output directory; existing evidence is preserved")
    source = args.experiment / "plan.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    types = original["assetTypes"]
    training = original["trainingSymbols"]
    symbols = ([s for s in training if types[s] == "stock"][:24]
               + [s for s in training if types[s] == "etf"][:8])
    splits = {k: v for k, v in original["splits"].items() if k.startswith("train")}
    args.output.mkdir(parents=True)
    plan = {
        "sourcePlanSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "symbols": symbols, "splits": splits, "seed": 42, "policySteps": 256,
        "maxSeconds": 180, "poolSwitchInterval": 4,
        "purpose": "execution_training_smoke_not_performance_evaluation",
    }
    (args.output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    frames = {}
    for symbol in symbols:
        frame = pd.read_csv(args.experiment / "data" / f"{symbol}.csv")
        frames[symbol] = frame.loc[
            pd.to_datetime(frame["date"]) <= pd.Timestamp(splits["trainEndDate"])
        ].copy()
    _, report = train_masked(
        frames, asset_types=types, splits=splits, destination=args.output / "model",
        steps=256, max_seconds=180, pool_switch_interval=4,
        costs=TradingCosts(0.03, 0.05, 0.02, stamp_duty_mode="asset_date"),
    )
    if report["actualSteps"] != 256 or report["optimizerUpdates"] != 225:
        raise AssertionError("smoke did not complete registered budget")
    if report["poolEventCount"] < 1 or report["marketSteps"] != 256 + report["poolEventCount"]:
        raise AssertionError("missing switch execution evidence")
    if any(e["actionApplied"] for e in report["poolEvents"]):
        raise AssertionError("exogenous event recorded as policy action")
    result = {
        "planSha256": hashlib.sha256((args.output / "plan.json").read_bytes()).hexdigest(),
        "training": report, "testEvaluationExecuted": False,
        "productionChanges": 0, "performanceImprovementClaimed": False,
    }
    (args.output / "report.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in
                      ("actualSteps", "optimizerUpdates", "marketSteps", "poolEventCount")}))


if __name__ == "__main__":
    main()
