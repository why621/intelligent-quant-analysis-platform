"""Build independent assets without fetching or splicing adjustment series."""

import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from quant_platform.data.coverage import assess_history, digest
from quant_platform.data.index_snapshot import load_index
from quant_platform.data.publication import PublishedProvider, checked_document
from quant_platform.data.trading_events import load_events
from quant_platform.data.universe import load_snapshot
from tools.prepare_history_batch import load_observation, validate_observation


def build_partial(
    output, start, end, baseline, universe_dir, event_path, stage_errors=None
):
    previous = PublishedProvider(baseline)
    universe = load_snapshot(universe_dir)
    if universe.to_dict() != previous.universe_snapshot.to_dict():
        raise ValueError("partial publication requires the same constituent snapshot")
    events = load_events(event_path)
    histories, errors, manifests, sources = {}, {}, {}, []
    stages = dict(stage_errors or {})
    for stage in ("stocks", "etfs"):
        path = output / stage / "manifest.json"
        if not path.exists():
            continue
        try:
            manifest = checked_document(path)
            if manifest.get("candidateId") != digest(
                {k: v for k, v in manifest.items() if k != "candidateId"}
            ):
                raise ValueError("source manifest hash mismatch")
            if (manifest["startDate"], manifest["endDate"]) != (
                start.isoformat(),
                end.isoformat(),
            ):
                raise ValueError("source interval mismatch")
            if (
                stage == "stocks"
                and manifest["universeVersion"] != universe.to_dict()["snapshotId"]
            ):
                raise ValueError("source universe mismatch")
            manifests[stage] = {
                e.get("symbol", e.get("asset", {}).get("symbol")): e
                for e in manifest["entries"]
            }
            sources.append(manifest["candidateId"])
        except (OSError, KeyError, ValueError, TypeError) as exc:
            stages[stage] = f"source manifest rejected: {type(exc).__name__}"
    for symbol, asset in previous._assets.items():
        stage = "stocks" if asset.asset_type == "stock" else "etfs"
        entry = manifests.get(stage, {}).get(symbol)
        rows = None
        try:
            if entry is None:
                raise ValueError("asset not collected or stage incomplete")
            wrapper = load_observation(
                output / stage / "observations" / (symbol + ".json")
            )
            if wrapper["sha256"] != entry["observationSha256"]:
                raise ValueError("observation hash differs from manifest")
            observation = wrapper["observation"]
            validate_observation(observation, symbol, start, end)
            if observation["error"]:
                raise ValueError("upstream request failed")
            quality = assess_history(
                pd.DataFrame(observation["records"]),
                start,
                end,
                events=events,
                asset_id=f"{asset.asset_type}:{asset.exchange}:{symbol}",
            )
            if quality["status"] not in {
                "complete",
                "complete_with_exceptions",
                "gaps",
            }:
                raise ValueError("empty or invalid candidate prices")
            rows = observation["records"]
            if quality["status"] == "gaps":
                errors[symbol] = "unexplained trading-day gaps"
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors[symbol] = str(exc)[:200]
        if rows is None:
            rows = [
                r
                for r in baseline["histories"][symbol]
                if start.isoformat() <= r["date"][:10] <= end.isoformat()
            ]
        histories[symbol] = rows
    index_raw = baseline.get("indexRaw")
    index_window = copy.deepcopy(
        baseline.get(
            "indexWindow",
            {
                "startDate": baseline["startDate"],
                "endDate": baseline["endDate"],
            },
        )
    )
    try:
        index = load_index(output / "index")
        if (index.start, index.end) != (start, end):
            raise ValueError("index interval mismatch")
        index_raw = (output / "index" / "response.txt").read_text()
        index_window = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    except (OSError, KeyError, ValueError, TypeError):
        stages.setdefault("index", "index update unavailable; previous index retained")
    value = {
        "schemaVersion": 2,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "createdAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "universe": universe.to_dict(),
        "tradingEvents": [e.to_dict() for e in events],
        "indexRaw": index_raw,
        "indexWindow": index_window,
        "sourceCandidates": sources,
        "histories": histories,
        "assetErrors": errors,
        "stageErrors": stages,
    }
    document = {**value, "publicationId": digest(value)}
    provider = PublishedProvider(document)
    advanced = any(
        a["lastTradeDate"] and a["lastTradeDate"] > previous.end.isoformat()
        for a in provider.availability["assets"].values()
    ) or (
        provider.index_snapshot is not None
        and provider.index_snapshot.end > previous.end
    )
    if not advanced:
        raise ValueError("no independently validated data advanced")
    return document
