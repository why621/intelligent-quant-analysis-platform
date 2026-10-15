"""Freeze CR069 inputs from an existing publication, with no market downloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from quant_platform.data.publication import load_publication


def prepare(source: Path, destination: Path) -> dict:
    provider = load_publication(source)
    pointer = json.loads((source / "current.json").read_text(encoding="utf-8"))
    published = source / "releases" / (pointer["publicationId"] + ".json")
    assets = {a.symbol: a for a in provider.list_assets(limit=None)}
    frames = {
        s: provider.history(s, provider.start, provider.end, "qfq") for s in assets
    }
    dates = pd.DatetimeIndex(frames["510300"].date)
    if len(dates) < 243:
        raise ValueError("experiment requires at least 243 real reference sessions")
    complete = sorted(
        s for s, f in frames.items() if pd.DatetimeIndex(f.date).equals(dates)
    )
    held_out = []
    for kind, count in (("stock", 32), ("etf", 8)):
        eligible = [s for s in complete if assets[s].asset_type == kind]
        ordered = sorted(
            eligible,
            key=lambda s: hashlib.sha256(("cr069-heldout:" + s).encode()).hexdigest(),
        )
        if len(ordered) < count + 10:
            raise ValueError("insufficient stratified training/held-out assets")
        held_out.extend(ordered[:count])
    training = sorted(set(complete) - set(held_out))
    stocks = [s for s in training if assets[s].asset_type == "stock"]
    etfs = [s for s in training if assets[s].asset_type == "etf"]
    groups = {
        "stocks": stocks[:10],
        "etfs": etfs[:10],
        "mixed": stocks[-5:] + etfs[-5:],
    }
    split_index = (0, 199, 200, 219, 220, len(dates) - 1)
    split_keys = (
        "trainStartDate",
        "trainEndDate",
        "valStartDate",
        "valEndDate",
        "testStartDate",
        "testEndDate",
    )
    splits = {
        k: dates[i].date().isoformat()
        for k, i in zip(split_keys, split_index, strict=True)
    }
    report = {
        "schemaVersion": 1,
        "evidenceKind": "existing_real_publication_readonly",
        "source": str(published),
        "sourceSha256": hashlib.sha256(published.read_bytes()).hexdigest(),
        "publicationId": pointer["publicationId"],
        "universeVersion": provider.publication_context["universeVersion"],
        "symbols": sorted(assets),
        "assetTypes": {s: assets[s].asset_type for s in sorted(assets)},
        "trainingSymbols": training,
        "heldOutSymbols": sorted(held_out),
        "irregularHistorySymbols": sorted(set(assets) - set(complete)),
        "barsPerAsset": {s: len(f) for s, f in frames.items()},
        "splits": splits,
        "validationGroups": groups,
        "selection": "mean_validation_return_minus_drawdown_across_frozen_stock_etf_mixed_groups",
        "seeds": [42, 137],
        "stepsPerCandidate": 65536,
        "maxSecondsPerCandidate": 1200,
        "newMarketRequests": 0,
        "limitations": [
            "about one year of existing data; short validation and test",
            "test dates were previously used by CR065/066; not a pristine blind temporal test",
            "current constituent membership can introduce survivorship bias",
            "held-out assets excluded from gradients and validation selection; no profitability claim",
        ],
    }
    if destination.exists():
        raise ValueError(
            "experiment directory exists; refusing to overwrite frozen inputs"
        )
    (destination / "data").mkdir(parents=True)
    for symbol, frame in frames.items():
        frame.to_csv(destination / "data" / (symbol + ".csv"), index=False)
    report["dataHashes"] = {
        s: hashlib.sha256(
            (destination / "data" / (s + ".csv")).read_bytes()
        ).hexdigest()
        for s in sorted(assets)
    }
    (destination / "plan.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.publication, args.output)
    print(
        json.dumps(
            {
                "assets": len(result["symbols"]),
                "training": len(result["trainingSymbols"]),
                "heldOut": len(result["heldOutSymbols"]),
                "splits": result["splits"],
            }
        )
    )


if __name__ == "__main__":
    main()
