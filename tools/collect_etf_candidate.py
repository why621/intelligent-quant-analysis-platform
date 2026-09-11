"""Bounded fixed 27-ETF candidate; isolated output only, no publication or retry."""

import argparse
from datetime import date
from pathlib import Path
from time import monotonic, sleep

import pandas as pd
from quant_platform.data.akshare_provider import _DEFAULT_UNIVERSE
from quant_platform.data.coverage import assess_history, digest

from tools.collect_history_universe import atomic
from tools.prepare_history_batch import fetch_one, new_output, validate_observation


def collect(output, start, end, *, fetch=fetch_one, pause=sleep):
    assets = [a for a in _DEFAULT_UNIVERSE if a["asset_type"] == "etf"]
    output.mkdir(parents=True, exist_ok=False)
    (output / "observations").mkdir()
    document = {
        "kind": "isolated_etf_candidate",
        "published": False,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "requestBudget": 135,
        "secondsBudget": 1200,
        "requestUpperBoundThisRun": 0,
        "entries": [],
    }
    began = monotonic()
    failures = 0
    for asset in assets:
        if monotonic() - began + 41 > 1200 or failures >= 3:
            break
        symbol = asset["symbol"]
        document["requestUpperBoundThisRun"] += 5
        document["inFlight"] = symbol
        atomic(output / "manifest.json", document)
        value = fetch(symbol, start, end)
        validate_observation(value, symbol, start, end)
        atomic(
            output / "observations" / (symbol + ".json"),
            {"observation": value, "sha256": digest(value)},
        )
        quality = (
            None
            if value["error"]
            else assess_history(pd.DataFrame(value["records"]), start, end)
        )
        document["entries"].append(
            {
                "asset": asset,
                "observationSha256": digest(value),
                "quality": quality,
                "error": value["error"],
                "httpTrace": value["httpTrace"],
            }
        )
        failures = failures + 1 if value["error"] else 0
        document["inFlight"] = None
        atomic(output / "manifest.json", document)
        print(symbol, value["error"] or quality["status"], flush=True)
        pause(1)
    document["complete"] = len(document["entries"]) == 27 and all(
        e["quality"] and e["quality"]["status"] == "complete"
        for e in document["entries"]
    )
    document["candidateId"] = digest(document)
    atomic(output / "manifest.json", document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    output = new_output(args.output, Path("artifacts"))
    collect(output, args.start, args.end)


if __name__ == "__main__":
    main()
