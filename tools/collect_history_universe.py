"""Budgeted serial acquisition into an isolated candidate; never a production publisher."""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import pandas as pd
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.data.coverage import (
    assess_history,
    canonical_bytes,
    digest,
    expected_sessions,
)
from quant_platform.data.trading_events import load_events, validate_events
from quant_platform.data.universe import load_snapshot

from tools.prepare_history_batch import (
    fetch_one,
    load_observation,
    validate_observation,
    worker_environment,
)


@contextmanager
def locked(output):
    with (output / ".lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("candidate already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical_bytes(value))
    temp.replace(path)


def checked_path(root, name):
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("candidate file escapes output directory")
    return target


def run(
    snapshot,
    symbols,
    start,
    end,
    output,
    *,
    events=(),
    request_budget=150,
    seconds_budget=1200,
    resume=False,
    fetch=fetch_one,
    pause=sleep,
    seed=None,
    offline_reclassify=False,
):
    if offline_reclassify and seed is None:
        raise ValueError("offline reclassification requires a seed")
    events = validate_events(events)
    expected_sessions(start, end)
    members = {a.symbol: a for a in snapshot.members}
    if (
        not 1 <= len(symbols) <= 300
        or len(set(symbols)) != len(symbols)
        or any(s not in members for s in symbols)
    ):
        raise ValueError("invalid constituent selection")
    if not 5 <= request_budget <= 1500 or not 41 <= seconds_budget <= 14400:
        raise ValueError("invalid acquisition budget")
    if end > datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1):
        raise ValueError("uncompleted end date")
    config = {
        "universeVersion": snapshot.to_dict()["snapshotId"],
        "symbols": symbols,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "eventVersion": digest([e.to_dict() for e in events]),
        "requestBudget": request_budget,
        "secondsBudget": seconds_budget,
    }
    if offline_reclassify:
        config["offlineReclassify"] = True
    seeded = {}
    if seed is not None:
        source = json.loads((seed / "manifest.json").read_text())
        if source["candidateId"] != digest(
            {k: v for k, v in source.items() if k != "candidateId"}
        ):
            raise ValueError("seed manifest hash mismatch")
        if any(
            source[k] != config[k]
            for k in (
                ("universeVersion", "startDate", "endDate")
                if offline_reclassify
                else ("universeVersion", "startDate", "endDate", "eventVersion")
            )
        ):
            raise ValueError("seed configuration mismatch")
        config["seedCandidateId"] = source["candidateId"]
        for entry in source["entries"]:
            symbol = entry["symbol"]
            if symbol in symbols and entry["status"] in (
                {
                    "complete",
                    "complete_with_exceptions",
                }
                | ({"gaps"} if offline_reclassify else set())
            ):
                wrapper = load_observation(
                    checked_path(seed, f"observations/{symbol}.json")
                )
                validate_observation(wrapper["observation"], symbol, start, end)
                if (
                    wrapper["universeVersion"] != config["universeVersion"]
                    or wrapper["sha256"] != entry["observationSha256"]
                ):
                    raise ValueError("seed observation mismatch")
                seeded[symbol] = wrapper
    if fetch is fetch_one and not offline_reclassify:
        subprocess.run(
            [sys.executable, "-c", "import quant_platform.data.history_probe"],
            env=worker_environment(),
            check=True,
            capture_output=True,
            timeout=15,
        )
    if resume:
        if not output.is_dir():
            raise ValueError("resume directory absent")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "observations").mkdir()
    with locked(output):
        ledger_path = checked_path(output, "ledger.json")
        if resume:
            ledger = json.loads(ledger_path.read_text())
            if ledger["config"] != config:
                raise ValueError("resume configuration mismatch")
        else:
            ledger = {
                "config": config,
                "createdAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "reservedRequests": 0,
                "chargedSeconds": 0.0,
                "attempts": {},
                "cacheHashes": {},
            }
            for symbol, wrapper in seeded.items():
                atomic(checked_path(output, f"observations/{symbol}.json"), wrapper)
                ledger["attempts"][symbol] = "seed"
            atomic(ledger_path, ledger)
        if (
            set(ledger["attempts"]) - set(symbols)
            or ledger["reservedRequests"]
            != sum(v != "seed" for v in ledger["attempts"].values()) * 5
            or not 0 <= ledger["reservedRequests"] <= request_budget
            or ledger["chargedSeconds"] < 0
        ):
            raise ValueError("invalid ledger budget accounting")
        # Validate all prior evidence before constructing or mutating cache.
        observations = {}
        for symbol in ledger["attempts"]:
            path = checked_path(output, f"observations/{symbol}.json")
            if path.exists():
                value = load_observation(path)
                if value["universeVersion"] != config["universeVersion"]:
                    raise ValueError("observation universe mismatch")
                validate_observation(value["observation"], symbol, start, end)
                observations[symbol] = value
        provider = AkShareMarketDataProvider(
            output / "candidate-cache",
            universe_snapshot=snapshot,
            trading_events=events,
        )

        validated_cache = set()

        def checkpoint():
            entries = []
            for asset in snapshot.members:
                symbol = asset.symbol
                entry = {
                    "assetId": f"stock:{asset.exchange}:{symbol}",
                    "symbol": symbol,
                    "exchange": asset.exchange,
                    "status": "not_attempted",
                    "quality": None,
                    "observationSha256": None,
                    "error": None,
                }
                if symbol in ledger["attempts"] and symbol not in observations:
                    entry.update(
                        status="source_error",
                        error="interrupted_attempt_request_count_unknown",
                    )
                if symbol in observations:
                    wrapper = observations[symbol]
                    value = wrapper["observation"]
                    entry.update(
                        observationSha256=wrapper["sha256"], error=value["error"]
                    )
                    if value["error"]:
                        entry["status"] = "source_error"
                    else:
                        frame = pd.DataFrame(value["records"])
                        quality = assess_history(
                            frame, start, end, events=events, asset_id=entry["assetId"]
                        )
                        entry.update(status=quality["status"], quality=quality)
                        if (
                            quality["status"]
                            in {"complete", "complete_with_exceptions"}
                            and ledger["cacheHashes"].get(symbol) != wrapper["sha256"]
                        ):
                            provider._save_history_cache(symbol, frame)
                            ledger["cacheHashes"][symbol] = wrapper["sha256"]
                        if quality["status"] in {
                            "complete",
                            "complete_with_exceptions",
                        }:
                            cached = provider._load_history_cache(symbol)
                            expected = frame.copy()
                            expected["date"] = pd.to_datetime(expected["date"])
                            expected = expected.reindex(columns=cached.columns)
                            if json.loads(
                                cached.to_json(orient="records", date_format="iso")
                            ) != json.loads(
                                expected.to_json(orient="records", date_format="iso")
                            ):
                                raise ValueError(
                                    "candidate cache differs from validated observation"
                                )
                            validated_cache.add(symbol)
                entries.append(entry)
            counts = dict(Counter(e["status"] for e in entries))
            acquired = {
                s: w for s, w in observations.items() if ledger["attempts"][s] != "seed"
            }
            known = sum(
                len(w["observation"]["httpTrace"] or []) for w in acquired.values()
            )
            exact = len(observations) == len(ledger["attempts"]) and all(
                w["observation"]["httpTrace"] is not None for w in acquired.values()
            )
            manifest = {
                "schemaVersion": 3,
                "kind": "isolated_history_candidate",
                "published": False,
                "universeVersion": config["universeVersion"],
                "membershipMode": "current_snapshot",
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "adjust": "qfq",
                "source": "Tencent",
                "sdkVersion": "1.18.94",
                "normalizationVersion": "tx-1.18.94-project-v1",
                "volumeUnit": "share",
                "amountUnit": "CNY",
                "createdAt": ledger["createdAt"],
                "mode": "offline_replay" if offline_reclassify else "live_probe",
                "selectedSymbols": symbols,
                "memberCount": 300,
                "statusCounts": counts,
                "priceCoverageComplete": sum(
                    counts.get(k, 0) for k in ("complete", "complete_with_exceptions")
                )
                == 300,
                "candidateRevision": provider.cache_revision(),
                "networkRequestsThisRun": known,
                "requestCountExact": exact,
                "requestUpperBoundThisRun": ledger["reservedRequests"],
                "requestBudget": request_budget,
                "secondsBudget": seconds_budget,
                "chargedSeconds": ledger["chargedSeconds"],
                "entries": entries,
                "tradingEvents": [e.to_dict() for e in events],
                "eventVersion": config["eventVersion"],
            }
            if seed is not None:
                manifest["seedCandidateId"] = config["seedCandidateId"]
                manifest["seededAssetCount"] = len(seeded)
            manifest["candidateId"] = digest(manifest)
            atomic(ledger_path, ledger)
            atomic(checked_path(output, "manifest.json"), manifest)
            return manifest

        checkpoint()
        consecutive_failures = 0
        for symbol in symbols:
            if offline_reclassify:
                break
            if symbol in ledger["attempts"]:
                continue  # Even interrupted calls are not retried without a new explicit plan.
            if (
                ledger["reservedRequests"] + 5 > request_budget
                or ledger["chargedSeconds"] + 41 > seconds_budget
            ):
                break
            ledger["attempts"][symbol] = "reserved"
            ledger["reservedRequests"] += 5
            ledger["chargedSeconds"] += (
                41  # Keep conservative charge if killed mid-worker.
            )
            atomic(ledger_path, ledger)
            began = monotonic()
            value = fetch(symbol, start, end)
            validate_observation(value, symbol, start, end)
            wrapper = {
                "universeVersion": config["universeVersion"],
                "observation": value,
                "sha256": digest(value),
            }
            atomic(checked_path(output, f"observations/{symbol}.json"), wrapper)
            observations[symbol] = wrapper
            pause(1)
            ledger["attempts"][symbol] = "finished"
            ledger["chargedSeconds"] += monotonic() - began - 41
            manifest = checkpoint()
            print(
                json.dumps(
                    {
                        "symbol": symbol,
                        "statusCounts": manifest["statusCounts"],
                        "requestsKnown": manifest["networkRequestsThisRun"],
                        "requestsReserved": ledger["reservedRequests"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            consecutive_failures = consecutive_failures + 1 if value["error"] else 0
            if consecutive_failures >= 3:
                break
        return checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--request-budget", type=int, default=150)
    parser.add_argument("--seconds-budget", type=int, default=1200)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--offline-reclassify", action="store_true")
    args = parser.parse_args()
    root = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
    output = args.output.resolve()
    if output == root or not output.is_relative_to(root):
        parser.error("output must be an artifacts child")

    if args.seed and not args.seed.resolve().is_relative_to(root):
        parser.error("seed must be an artifacts child")

    def timeout(signum, frame):
        raise TimeoutError("acquisition deadline reached; resume uses reserved budget")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.seconds_budget)
    try:
        run(
            load_snapshot(args.snapshot),
            args.symbols,
            args.start,
            args.end,
            output,
            events=load_events(args.events),
            request_budget=args.request_budget,
            seconds_budget=args.seconds_budget,
            resume=args.resume,
            seed=args.seed,
            offline_reclassify=args.offline_reclassify,
        )
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
