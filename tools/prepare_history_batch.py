"""Collect <=6 current constituents into a NEW isolated candidate, or replay offline.

No default pool switch, publication status, overview request or production writes.
Run under Linux with PYTHONPATH=services/algorithms/src and the project venv.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
from collections import Counter
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
from quant_platform.data.universe import UniverseSnapshot, load_snapshot

MAX_ASSETS = 6
MAX_FILE_BYTES = 2 * 1024 * 1024


def new_output(path: Path, artifact_root: Path) -> Path:
    output, root = path.resolve(), artifact_root.resolve()
    if not output.is_relative_to(root) or output == root or output.exists():
        raise ValueError("output must be a NEW child directory of artifacts")
    return output


def fetch_one(symbol: str, start: date, end: date) -> dict:
    payload = {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()}
    try:
        process = subprocess.run(
            [sys.executable, "-m", "quant_platform.data.history_probe"],
            input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
            timeout=40, check=True,
        )
        if len(process.stdout.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("worker output oversized")
        return json.loads(process.stdout)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        return {**payload, "adjust": "qfq", "source": "Tencent", "sdkVersion": "1.18.94",
                "normalizationVersion": "tx-1.18.94-project-v1",
                "retrievedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "records": [], "httpTrace": None, "error": type(exc).__name__}


def load_observation(path: Path) -> dict:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("observation oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["sha256"] != digest(value["observation"]):
        raise ValueError("observation hash mismatch")
    return value


def validate_observation(value: dict, symbol: str, start: date, end: date):
    expected = {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
                "adjust": "qfq", "source": "Tencent", "sdkVersion": "1.18.94",
                "normalizationVersion": "tx-1.18.94-project-v1"}
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("observation identity, interval or provenance mismatch")
    fetched = datetime.fromisoformat(value["retrievedAt"])
    if fetched.tzinfo is None or fetched.astimezone(ZoneInfo("Asia/Shanghai")).date() <= end:
        raise ValueError("observation timestamp does not establish a completed interval")
    if not isinstance(value.get("records"), list) or len(value["records"]) > 1000:
        raise ValueError("invalid or oversized history records")
    trace = value.get("httpTrace")
    if trace is not None and (not isinstance(trace, list) or len(trace) > 5):
        raise ValueError("invalid HTTP budget evidence")
    if trace is None and not value.get("error"):
        raise ValueError("successful observation requires request evidence")


def prepare_batch(snapshot: UniverseSnapshot, symbols: list[str], start: date, end: date,
                  output: Path, *, replay: Path | None = None, fetch=fetch_one,
                  pause=sleep) -> dict:
    expected_sessions(start, end)
    members = {asset.symbol: asset for asset in snapshot.members}
    if not 1 <= len(symbols) <= MAX_ASSETS or len(set(symbols)) != len(symbols):
        raise ValueError("select 1 to 6 distinct constituents")
    if any(symbol not in members for symbol in symbols):
        raise ValueError("selected symbol is not in the verified membership snapshot")
    if end > datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1):
        raise ValueError("end date must precede today's uncompleted session")
    snapshot_id = snapshot.to_dict()["snapshotId"]
    # Resolve every replay input and validate before creating any output/SQLite.
    replayed = {}
    if replay:
        for symbol in symbols:
            wrapper = load_observation(replay / "observations" / f"{symbol}.json")
            if wrapper["universeVersion"] != snapshot_id:
                raise ValueError("replay belongs to another universe snapshot")
            validate_observation(wrapper["observation"], symbol, start, end)
            replayed[symbol] = wrapper["observation"]
    output.mkdir(parents=True, exist_ok=False)
    (output / "observations").mkdir()
    provider = AkShareMarketDataProvider(output / "candidate-cache", universe_snapshot=snapshot)
    observations, entries = {}, []
    deadline = monotonic() + 300
    for symbol in symbols:
        if monotonic() >= deadline:
            break
        value = replayed[symbol] if replay else fetch(symbol, start, end)
        validate_observation(value, symbol, start, end)
        wrapper = {"universeVersion": snapshot_id, "observation": value, "sha256": digest(value)}
        (output / "observations" / f"{symbol}.json").write_bytes(canonical_bytes(wrapper))
        observations[symbol] = wrapper
        if not replay:
            pause(1)
        print(f"Captured {symbol}: {value['error'] or str(len(value['records'])) + ' rows'}",
              flush=True)
    for asset in snapshot.members:
        wrapper = observations.get(asset.symbol)
        entry = {"assetId": f"stock:{asset.exchange}:{asset.symbol}", "symbol": asset.symbol,
                 "exchange": asset.exchange, "status": "not_attempted", "quality": None,
                 "observationSha256": None, "error": None}
        if wrapper is not None:
            value = wrapper["observation"]
            entry["observationSha256"] = wrapper["sha256"]
            entry["error"] = value["error"]
            if value["error"]:
                entry["status"] = "source_error"
            else:
                frame = pd.DataFrame(value["records"])
                quality = assess_history(frame, start, end)
                entry.update(status=quality["status"], quality=quality)
                if quality["status"] == "complete":
                    # A new isolated cache only; global DataStatus remains unready.
                    provider._save_history_cache(asset.symbol, frame, "qfq")
        entries.append(entry)
    counts = dict(Counter(entry["status"] for entry in entries))
    manifest = {
        "schemaVersion": 1, "kind": "isolated_history_candidate", "published": False,
        "universeVersion": snapshot_id, "membershipMode": "current_snapshot",
        "startDate": start.isoformat(), "endDate": end.isoformat(), "adjust": "qfq",
        "source": "Tencent", "sdkVersion": "1.18.94",
        "normalizationVersion": "tx-1.18.94-project-v1",
        "volumeUnit": "share", "amountUnit": "CNY",
        "createdAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "mode": "offline_replay" if replay else "live_probe",
        "selectedSymbols": symbols, "memberCount": 300, "statusCounts": counts,
        "priceCoverageComplete": counts.get("complete", 0) == 300,
        "candidateRevision": provider.cache_revision(),
        "networkRequestsThisRun": (0 if replay else
            sum(len(item["observation"]["httpTrace"]) for item in observations.values()
                if item["observation"]["httpTrace"] is not None)),
        "requestCountExact": replay is not None or all(
            item["observation"]["httpTrace"] is not None for item in observations.values()),
        "requestUpperBoundThisRun": 0 if replay else len(observations) * 5,
        "entries": entries,
    }
    manifest["candidateId"] = digest(manifest)
    temporary = output / "manifest.tmp"
    temporary.write_bytes(canonical_bytes(manifest))
    temporary.replace(output / "manifest.json")
    print(json.dumps({key: item for key, item in manifest.items() if key != "entries"},
                     ensure_ascii=False, indent=2))
    return manifest


def _deadline(_signum, _frame):
    raise TimeoutError("candidate batch exceeded 300 seconds; observations retained, not published")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    root = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
    output = new_output(args.output, root)
    if args.replay and not args.replay.resolve().is_relative_to(root):
        parser.error("replay must be within artifacts")
    snapshot = load_snapshot(args.snapshot)
    if not hasattr(signal, "SIGALRM"):
        parser.error("Linux required for batch hard deadline")
    signal.signal(signal.SIGALRM, _deadline)
    signal.alarm(300)
    try:
        prepare_batch(snapshot, args.symbols, args.start, args.end, output, replay=args.replay)
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
