"""Train CR069 candidates on frozen local inputs; select with validation only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from quant_platform.models import TradingCosts
from quant_platform.rl.portfolio_evaluation import evaluate_portfolio
from quant_platform.rl.portfolio_policy import load_portfolio_bundle
from quant_platform.rl.portfolio_train import train_portfolio, training_frames


def training_hashes(frames, splits):
    result = {}
    for symbol, frame in training_frames(frames, splits).items():
        raw = frame[["date", "open", "high", "low", "close"]].copy()
        raw["date"] = pd.to_datetime(raw["date"]).dt.strftime("%Y-%m-%d")
        for column in ("open", "high", "low", "close"):
            raw[column] = raw[column].astype(float)
        result[symbol] = hashlib.sha256(
            raw.to_csv(index=False, float_format="%.17g", lineterminator="\n").encode()
        ).hexdigest()
    return result


def validate_candidate(manifest, plan, hashes, algo, seed):
    expected = {
        "purpose": "formal_candidate",
        "algo": algo,
        "seed": seed,
        "splits": plan["splits"],
        "dataHashes": hashes,
        "requestedTimesteps": plan["stepsPerCandidate"],
        "maxSeconds": plan["maxSecondsPerCandidate"],
        "tradingCosts": {
            "commissionPct": 0.03,
            "slippagePct": 0.02,
            "stampDutyPct": 0.05,
            "stampDutyMode": "asset_date",
        },
    }
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError(
            "saved candidate differs from frozen data, dates, costs or training budget"
        )
    if set(manifest["trainingUniverse"]) != set(plan["trainingSymbols"]):
        raise ValueError("saved candidate differs from frozen training pool")


def train(experiment: Path) -> dict:
    plan_bytes = (experiment / "plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    frames = {}
    for symbol in plan["trainingSymbols"]:
        path = experiment / "data" / (symbol + ".csv")
        if hashlib.sha256(path.read_bytes()).hexdigest() != plan["dataHashes"][symbol]:
            raise ValueError("frozen history changed: " + symbol)
        frames[symbol] = pd.read_csv(path, dtype={"symbol": str})
    if set(frames) & set(plan["heldOutSymbols"]):
        raise ValueError("held-out assets leaked into training")
    out = experiment / "models"
    out.mkdir(exist_ok=True)
    report = {
        "planSha256": hashlib.sha256(plan_bytes).hexdigest(),
        "candidates": {},
        "selected": {},
    }
    splits = plan["splits"]
    hashes = training_hashes(frames, splits)
    for algo in ("ppo", "sac", "td3"):
        candidates = []
        for seed in plan["seeds"]:
            run_id = f"cr069-{algo}-universe-s{seed}"
            path = out / run_id
            if not path.exists():
                path = train_portfolio(
                    frames,
                    asset_types=plan["assetTypes"],
                    trading_costs=TradingCosts(stamp_duty_mode="asset_date"),
                    splits=splits,
                    output_root=out,
                    run_id=run_id,
                    algo=algo,
                    total_timesteps=plan["stepsPerCandidate"],
                    max_seconds=plan["maxSecondsPerCandidate"],
                    episode_bars=48,
                    seed=seed,
                    band_pct=0.01,
                    min_trade_cny=100,
                    formal_candidate=True,
                )
            bundle = load_portfolio_bundle(path)
            validate_candidate(bundle.manifest, plan, hashes, algo, seed)
            if bundle.manifest["actualTimesteps"] < plan["stepsPerCandidate"]:
                raise ValueError("candidate stopped before the frozen training budget")
            if set(bundle.manifest["trainingUniverse"]) != set(frames):
                raise ValueError("saved candidate does not match frozen training pool")
            validations = {
                name: evaluate_portfolio(
                    bundle,
                    {s: frames[s] for s in symbols},
                    start=splits["valStartDate"],
                    end=splits["valEndDate"],
                )
                for name, symbols in plan["validationGroups"].items()
            }
            scores = [
                v["metrics"]["returnPct"] - v["metrics"]["maxDrawdownPct"]
                for v in validations.values()
            ]
            item = {
                "runId": run_id,
                "bundleHash": bundle.manifest["bundleHash"],
                "score": sum(scores) / len(scores),
                "validation": {k: v["metrics"] for k, v in validations.items()},
                "steps": bundle.manifest["actualTimesteps"],
                "optimizerUpdates": bundle.manifest["optimizerUpdates"],
            }
            (path / "validation.json").write_text(
                json.dumps(validations, indent=2) + "\n", encoding="utf-8"
            )
            candidates.append(item)
            report["candidates"][run_id] = item
            (experiment / "training-report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(item), flush=True)
        report["selected"][algo] = max(candidates, key=lambda x: x["score"])
    # This file is frozen before any held-out asset or temporal test replay.
    selection = experiment / "selection.json"
    encoded = json.dumps(report["selected"], sort_keys=True, indent=2) + "\n"
    if selection.exists() and selection.read_text(encoding="utf-8") != encoded:
        raise ValueError("refusing to replace an existing frozen selection")
    selection.write_text(encoded, encoding="utf-8")
    (experiment / "training-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    train(args.experiment)


if __name__ == "__main__":
    main()
