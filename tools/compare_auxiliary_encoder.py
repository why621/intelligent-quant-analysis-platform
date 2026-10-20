"""Frozen train/validation-only auxiliary encoder update isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from diagnose_masked_training import CHECKPOINTS, STEPS, summarize_diagnostics, write
from quant_platform.models import TradingCosts
from quant_platform.rl.masked_train import (
    evaluate_research,
    load_research,
    train_masked,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; preserve evidence")
    source = args.experiment / "plan.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    reference_file = args.reference / "report.json"
    reference = json.loads(reference_file.read_text(encoding="utf-8"))
    reference_plan = json.loads((args.reference / "frozen-plan.json").read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if reference_plan["sourcePlanSha256"] != source_hash:
        raise ValueError("reference source plan differs")
    training = original["trainingSymbols"]
    groups = original["validationGroups"]
    splits = {k: v for k, v in original["splits"].items() if k.startswith(("train", "val"))}
    if any(not set(group) <= set(training) for group in groups.values()):
        raise ValueError("validation must use training pool")
    runs = []
    for key in ("attention-scale100", "masked_attention-scale100"):
        run = next(r for r in reference["runs"] if r["key"] == key)
        path = Path(run.get("reusedFrom", args.reference / key))
        _, metadata = load_research(path)
        recorded = run["training"]
        for field in ("actualSteps", "optimizerUpdates", "dataHashes", "sampling", "splits"):
            if metadata[field] != recorded[field]:
                raise ValueError(f"reference evidence mismatch: {field}")
        if (metadata["actualSteps"] != STEPS or metadata["optimizerUpdates"] != STEPS - 31
                or metadata["seed"] != 42 or metadata["rewardScale"] != 100
                or metadata["splits"] != splits
                or metadata.get("maeEncoderLearningRate", 3e-4) != 3e-4):
            raise ValueError("reference configuration mismatch")
        runs.append({**run, "reusedFrom": str(path), "maeEncoderLearningRate": 3e-4,
                     "verifiedWeightsSha256": metadata["weightsSha256"]})
    args.output.mkdir(parents=True)
    frozen = {
        "sourcePlanSha256": source_hash,
        "referenceReportSha256": hashlib.sha256(reference_file.read_bytes()).hexdigest(),
        "referencePlanSha256": hashlib.sha256(
            (args.reference / "frozen-plan.json").read_bytes()
        ).hexdigest(),
        "trainingSymbols": training, "validationGroups": groups, "splits": splits,
        "seed": 42, "rewardScale": 100, "steps": STEPS, "checkpoints": CHECKPOINTS,
        "diagnosticInterval": 256, "maxSecondsPerCandidate": 600,
        "auxiliaryEncoderRates": [3e-4, 3e-5, 0],
        "decoderLearningRate": 3e-4, "testEvaluationExecuted": False,
        "scope": "single_seed_validation_diagnostic_not_release",
        "reused": [{"key": r["key"], "weightsSha256": r["verifiedWeightsSha256"]} for r in runs],
    }
    write(args.output / "frozen-plan.json", frozen)
    frames = {}
    for symbol in training:
        frame = pd.read_csv(args.experiment / "data" / f"{symbol}.csv")
        frames[symbol] = frame.loc[
            pd.to_datetime(frame["date"]) <= pd.Timestamp(splits["valEndDate"])
        ].copy()
    types = original["assetTypes"]
    costs = TradingCosts(0.03, 0.05, 0.02, stamp_duty_mode="asset_date")
    write(args.output / "progress.json", runs)
    for label, rate in (("reduced", 3e-5), ("zero", 0)):
        key = f"masked-encoder-{label}"
        destination = args.output / key
        print(json.dumps({"started": key, "rate": rate}), flush=True)
        _, metadata = train_masked(
            frames, asset_types=types, splits=splits, destination=destination,
            steps=STEPS, max_seconds=600, variant="masked_attention", reward_scale=100,
            seed=42, diagnostic_interval=256, checkpoints=CHECKPOINTS, costs=costs,
            mae_encoder_learning_rate=rate,
        )
        if metadata["actualSteps"] != STEPS or metadata["optimizerUpdates"] != STEPS - 31:
            raise RuntimeError("incomplete candidate; preserve partial evidence")
        for field in ("dataHashes", "sampling", "costs"):
            if metadata[field] != runs[0]["training"][field]:
                raise AssertionError(f"candidate reference mismatch: {field}")
        if rate == 0 and any(d["maeEncoderDeltaNorm"] != 0 for d in metadata["diagnostics"]):
            raise AssertionError("zero auxiliary rate moved encoder")
        validations = []
        for step in (*CHECKPOINTS, STEPS):
            path = destination if step == STEPS else destination.with_name(f"{key}-step-{step}")
            network, checkpoint = load_research(path)
            if checkpoint["maeEncoderLearningRate"] != rate:
                raise AssertionError("checkpoint auxiliary rate mismatch")
            rows = []
            for name, symbols in groups.items():
                result = evaluate_research(
                    network, {s: frames[s] for s in symbols}, asset_types=types, costs=costs,
                    start=splits["valStartDate"], end=splits["valEndDate"],
                    in_sample_end=splits["trainEndDate"],
                )
                rows.append({"group": name, **{k: v for k, v in result.items() if k != "curve"}})
            validations.append({
                "step": step, "rows": rows,
                "meanReturnPct": float(np.mean([r["totalReturnPct"] for r in rows])),
                "meanDrawdownPct": float(np.mean([r["maxDrawdownPct"] for r in rows])),
                "score": float(np.mean([r["totalReturnPct"] - r["maxDrawdownPct"] for r in rows])),
            })
        run = {
            "key": key, "training": metadata, "validationCurve": validations,
            "maeEncoderLearningRate": rate,
            "lastFourDiagnosticsMean": summarize_diagnostics(metadata["diagnostics"]),
        }
        runs.append(run)
        write(args.output / "progress.json", runs)
        print(json.dumps({"completed": key, "validation": validations[-1]}), flush=True)
    # Zero auxiliary encoder updates should reproduce the no-reconstruction policy exactly.
    if runs[-1]["validationCurve"] != runs[0]["validationCurve"]:
        raise AssertionError("zero-rate policy differs from no-reconstruction reference")
    write(args.output / "report.json", {
        "frozenPlanSha256": hashlib.sha256((args.output / "frozen-plan.json").read_bytes()).hexdigest(),
        "runs": runs, "testEvaluationExecuted": False,
        "zeroRateMatchesAttentionValidation": True,
        "conclusionBoundary": "validation diagnostic only; no generalization or release claim",
    })


if __name__ == "__main__":
    main()
