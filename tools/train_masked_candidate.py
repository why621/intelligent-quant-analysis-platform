"""One predeclared local formal candidate; test data never selects the weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
from evaluate_universe_candidates import write_json
from quant_platform.models import TradingCosts
from quant_platform.portfolio.execution import PORTFOLIO_EXECUTION_VERSION
from quant_platform.rl.masked_serving import MaskedServingPolicy
from quant_platform.rl.masked_train import train_masked
from quant_platform.rl.portfolio_evaluation import evaluate_portfolio
from quant_platform.rl.portfolio_features import (
    ENVIRONMENT_VERSION,
    observation_signature,
)
from quant_platform.rl.portfolio_policy import (
    load_portfolio_bundle,
    save_portfolio_bundle,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("new output directory required")
    original = json.loads((args.source / "plan.json").read_text(encoding="utf-8"))
    plan = {
        **original,
        "seeds": [42],
        "stepsPerCandidate": 65536,
        "maxSecondsPerCandidate": 3600,
        "poolSwitchInterval": 4,
        "rewardScale": 1,
        "maeEncoderLearningRate": 3e-5,
        "selection": "single_predeclared_final_checkpoint_no_test_selection",
        "limitations": [
            "EarnMore-inspired feature reconstruction, not a complete reproduction.",
            "One fixed candidate; no demonstrated excess return or convergence.",
            "Historical test window already examined; execution checks are not a blind alpha test.",
            "Runtime pool is fixed per web request; intra-episode switching is a training mechanism.",
        ],
    }
    args.output.mkdir(parents=True)
    write_json(args.output / "plan.json", plan)
    shutil.copytree(args.source / "data", args.output / "data")
    frames = {}
    for symbol in plan["trainingSymbols"]:
        path = args.output / "data" / f"{symbol}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != plan["dataHashes"][symbol]:
            raise ValueError("frozen training data changed")
        data = pd.read_csv(path)
        frames[symbol] = data.loc[
            pd.to_datetime(data["date"]) <= pd.Timestamp(plan["splits"]["valEndDate"])
        ].copy()
    network, training = train_masked(
        frames,
        asset_types=plan["assetTypes"],
        splits=plan["splits"],
        destination=args.output / "training",
        steps=65536,
        max_seconds=3600,
        seed=42,
        pool_switch_interval=4,
        mae_encoder_learning_rate=3e-5,
        formal_candidate=True,
        costs=TradingCosts(stamp_duty_mode="asset_date"),
    )
    if training["actualSteps"] != 65536 or training["optimizerUpdates"] != 65505:
        raise RuntimeError("incomplete formal budget; candidate cannot be released")
    metadata = {
        "schemaVersion": 1,
        "runId": "cr070-masked-sac-s42",
        "algo": "masked_sac",
        "architecture": "masked-set-sac-research-v1",
        "encoderWidth": 32,
        "variant": "masked_attention",
        "portfolioMode": "joint_portfolio",
        "environmentVersion": ENVIRONMENT_VERSION,
        "executionVersion": PORTFOLIO_EXECUTION_VERSION,
        "observationSignature": observation_signature(),
        "observationShape": [161],
        "actionShape": [11],
        "maxAssets": 10,
        "minAssets": 2,
        "generalization": "unverified",
        "performanceStatus": "unproven",
        "releaseEligible": False,
        "trainingUniverse": training["trainingUniverse"],
        "assetTypes": {s: plan["assetTypes"][s] for s in training["trainingUniverse"]},
        "dataHashes": training["dataHashes"],
        "splits": plan["splits"],
        "tradingCosts": training["costs"],
        "purpose": "formal_candidate",
        "actualTimesteps": training["actualSteps"],
        "optimizerUpdates": training["optimizerUpdates"],
        "requestedTimesteps": 65536,
        "seed": 42,
        "maxSeconds": 3600,
        "trainingEvidence": training,
        "rebalanceBandPct": 0,
        "minTradeCny": 0,
        "weightSelection": plan["selection"],
    }
    path = save_portfolio_bundle(
        MaskedServingPolicy(network), args.output / "models", metadata
    )
    bundle = load_portfolio_bundle(path)
    validation = {}
    for name, symbols in plan["validationGroups"].items():
        validation[name] = evaluate_portfolio(
            bundle,
            {s: frames[s] for s in symbols},
            start=plan["splits"]["valStartDate"],
            end=plan["splits"]["valEndDate"],
        )["metrics"]
    selected = {
        "masked_sac": {
            "runId": metadata["runId"],
            "bundleHash": bundle.manifest["bundleHash"],
            "validation": validation,
        }
    }
    write_json(args.output / "selection.json", selected)
    write_json(
        args.output / "training-report.json",
        {
            "planSha256": hashlib.sha256(
                (args.output / "plan.json").read_bytes()
            ).hexdigest(),
            "selected": selected,
            "training": training,
            "testEvaluationExecuted": False,
        },
    )
    print(
        json.dumps(
            {
                "candidate": metadata["runId"],
                "steps": training["actualSteps"],
                "marketSteps": training["marketSteps"],
                "validation": validation,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
