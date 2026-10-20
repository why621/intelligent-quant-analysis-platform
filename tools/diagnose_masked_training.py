"""Train/validation-only bounded diagnostics. Never evaluates the test partition."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.masked_train import (
    evaluate_research,
    load_research,
    train_masked,
)

STEPS = 4096
CHECKPOINTS = (1024, 2048)
CONFIGS = [(variant, scale) for variant in ("attention", "masked_attention") for scale in (1, 100)]


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def summarize_diagnostics(rows):
    if not rows:
        raise ValueError("diagnostics required")
    last = rows[-4:]
    means = {key: float(np.mean([row[key] for row in last])) for key in last[0] if key != "step"}
    means["entropyToScaledRewardRatio"] = (
        means["entropyTermAbsMean"] / max(means["scaledRewardAbsMean"], 1e-12)
    )
    means["actorEntropyToValueGradientRatio"] = (
        means["actorEntropyGradientNorm"] / max(means["actorValueGradientNorm"], 1e-12)
    )
    return means


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-seconds", type=int, choices=(180, 600), default=180)
    parser.add_argument("--reuse-completed", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; preserve evidence")
    source = args.experiment / "plan.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    training = original["trainingSymbols"]
    groups = original["validationGroups"]
    if any(not set(group) <= set(training) for group in groups.values()):
        raise ValueError("validation must stay inside the training stock pool")
    splits = {key: value for key, value in original["splits"].items()
              if key.startswith(("train", "val"))}
    args.output.mkdir(parents=True)
    frozen = {
        "sourcePlanSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "trainingSymbols": training, "validationGroups": groups, "splits": splits,
        "configs": CONFIGS, "seed": 42, "steps": STEPS, "checkpoints": CHECKPOINTS,
        "diagnosticInterval": 256, "maxSecondsPerCandidate": args.max_seconds,
        "testEvaluationExecuted": False, "scope": "diagnostic_screen_not_release_training",
    }
    reused = {}
    if args.reuse_completed:
        old_plan_path = args.reuse_completed / "frozen-plan.json"
        old = json.loads(old_plan_path.read_text(encoding="utf-8"))
        for key, value in frozen.items():
            # JSON represents tuples as lists.
            if (key != "maxSecondsPerCandidate"
                    and json.dumps(old[key], sort_keys=True) != json.dumps(value, sort_keys=True)):
                raise ValueError(f"reuse plan mismatch: {key}")
        completed = json.loads(
            (args.reuse_completed / "progress.json").read_text(encoding="utf-8")
        )
        for run in completed:
            _, metadata = load_research(args.reuse_completed / run["key"])
            if (metadata["actualSteps"] != STEPS
                    or metadata["dataHashes"] != run["training"]["dataHashes"]
                    or metadata["optimizerUpdates"] != STEPS - 31
                    or metadata["variant"] != run["training"]["variant"]
                    or metadata["rewardScale"] != run["training"]["rewardScale"]):
                raise ValueError("reused candidate incomplete or inconsistent")
            reused[run["key"]] = {**run, "reusedFrom": str(args.reuse_completed / run["key"])}
        frozen["reusePlanSha256"] = hashlib.sha256(old_plan_path.read_bytes()).hexdigest()
        frozen["reusedKeys"] = list(reused)
    write(args.output / "frozen-plan.json", frozen)
    # Do not load any held-out symbol. Discard dates after validation before use.
    frames = {}
    for symbol in training:
        frame = pd.read_csv(args.experiment / "data" / f"{symbol}.csv")
        frames[symbol] = frame.loc[
            pd.to_datetime(frame["date"]) <= pd.Timestamp(splits["valEndDate"])
        ].copy()
    types = original["assetTypes"]
    costs = TradingCosts(0.03, 0.05, 0.02, stamp_duty_mode="asset_date")
    runs = []
    for variant, scale in CONFIGS:
        key = f"{variant}-scale{scale}"
        if key in reused:
            runs.append(reused[key])
            write(args.output / "progress.json", runs)
            print(json.dumps({"reused": key}), flush=True)
            continue
        destination = args.output / key
        _, metadata = train_masked(
            frames, asset_types=types, splits=splits, destination=destination,
            steps=STEPS, max_seconds=args.max_seconds, variant=variant, reward_scale=scale,
            seed=42, diagnostic_interval=256, checkpoints=CHECKPOINTS, costs=costs,
        )
        if metadata["actualSteps"] != STEPS:
            raise RuntimeError("time budget exhausted; do not compare as complete training")
        validations = []
        for step in (*CHECKPOINTS, STEPS):
            path = destination if step == STEPS else destination.with_name(f"{key}-step-{step}")
            network, _ = load_research(path)
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
            "lastFourDiagnosticsMean": summarize_diagnostics(metadata["diagnostics"]),
        }
        runs.append(run)
        write(args.output / "progress.json", runs)
        print(json.dumps({
            "completed": key, "validation": [
                {k: row[k] for k in ("step", "meanReturnPct", "score")}
                for row in validations
            ], "diagnostics": run["lastFourDiagnosticsMean"],
        }), flush=True)
    if any(run["training"]["sampling"] != runs[0]["training"]["sampling"] for run in runs[1:]):
        raise AssertionError("sampling mismatch")
    if any(run["training"]["dataHashes"] != runs[0]["training"]["dataHashes"] for run in runs[1:]):
        raise AssertionError("training data mismatch")
    write(args.output / "report.json", {
        "frozenPlanSha256": hashlib.sha256((args.output / "frozen-plan.json").read_bytes()).hexdigest(),
        "runs": runs, "testEvaluationExecuted": False,
        "conclusionBoundary": "training diagnostics and reused validation only; no OOS claims",
    })


if __name__ == "__main__":
    main()
