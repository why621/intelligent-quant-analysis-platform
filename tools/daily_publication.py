"""Bounded local daily acceptance; actual scheduled evidence remains separately audited."""
import argparse
import json
import signal
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_platform.data.calendar import latest_session
from quant_platform.data.index_snapshot import save_index
from quant_platform.data.publication import (
    PublishedProvider,
    checked_document,
    load_publication,
    publish,
)
from quant_platform.data.trading_events import load_events
from quant_platform.data.universe import load_snapshot

from tools.build_publication import build
from tools.collect_etf_candidate import collect
from tools.collect_history_universe import atomic, locked, run
from tools.prepare_history_batch import worker_environment
from tools.verify_published_provider import verify

ROOT = Path("artifacts/cr025-daily-20260910")
BASE = Path("artifacts/cr024-publication-20260910")
UNIVERSE = Path("artifacts/cr012-universe-20260908")
TZ = ZoneInfo("Asia/Shanghai")


def consecutive(attempts):
    days = sorted({date.fromisoformat(a["targetDate"]) for a in attempts if a["status"] == "succeeded" and a["trigger"] == "scheduled"})
    return any(latest_session(b - timedelta(days=1)) == a for a, b in zip(days, days[1:]))


def pipeline(output, target):
    start = target.replace(year=target.year - 1)
    universe = load_snapshot(UNIVERSE)
    stock = run(universe, [a.symbol for a in universe.members], start, target, output / "stocks", events=load_events(Path("config/trading-events.json")), request_budget=1500, seconds_budget=3600)
    if not stock["priceCoverageComplete"]:
        raise ValueError("stock candidate incomplete; inspect stocks/manifest.json")
    etf = collect(output / "etfs", start, target)
    if not etf["complete"]:
        raise ValueError("ETF candidate incomplete; inspect etfs/manifest.json")
    result = subprocess.run([sys.executable, "-m", "tools.index_probe"], input=json.dumps({"start": start.isoformat(), "end": target.isoformat()}), capture_output=True, text=True, timeout=45, check=True, env=worker_environment())
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError("index worker output oversized")
    index = json.loads(result.stdout)
    save_index(index["raw"].encode("utf-8"), start, target, output / "index")
    atomic(output / "index" / "http-trace.json", index["httpTrace"])
    document = build(output / "stocks", output / "etfs", UNIVERSE, output / "index")
    atomic(output / "five-module.json", verify(PublishedProvider(document)))
    return document


def decision(state, target, baseline_end):
    attempts = state["attempts"]
    if consecutive(attempts):
        return "two_day_candidate_requires_scheduler_audit"
    if len(attempts) >= 4:
        return "budget_exhausted"
    if target <= baseline_end:
        return "waiting_new_day"
    if any(a["targetDate"] == target.isoformat() for a in attempts):
        return "already_attempted"
    return "eligible"


def execute(root, now, trigger, *, dry=False, build_candidate=pipeline, baseline=BASE):
    if trigger not in {"manual", "scheduled"} or now.tzinfo is None:
        raise ValueError("explicit trigger and timezone required")
    now = now.astimezone(TZ)
    target = latest_session(now.date() - timedelta(days=1))
    baseline_provider = load_publication(baseline)
    state_path = root / "state.json"
    state = checked_document(state_path) if state_path.exists() else {"attempts": []}
    status = decision(state, target, baseline_provider.end)
    if dry or status != "eligible":
        return {"decision": status, "targetDate": target.isoformat(), "dryRun": dry, "maxRequestsPerAttempt": 1637}
    root.mkdir(parents=True, exist_ok=True)
    with locked(root):
        state = checked_document(state_path) if state_path.exists() else {"attempts": []}
        status = decision(state, target, baseline_provider.end)
        if status != "eligible":
            return {"decision": status}
        output = root / target.isoformat()
        output.mkdir(exist_ok=False)
        attempt = {"targetDate": target.isoformat(), "startedAt": now.isoformat(), "trigger": trigger, "status": "running", "requestUpperBound": 1637}
        state["attempts"].append(attempt)
        atomic(state_path, state)
        try:
            if not (root / "publication" / "current.json").exists():
                pointer = checked_document(baseline / "current.json")
                publish(root / "publication", checked_document(baseline / "releases" / (pointer["publicationId"] + ".json")))
            document = build_candidate(output, target)
            candidate = PublishedProvider(document)
            if candidate.end != target or candidate.start != target.replace(year=target.year - 1):
                raise ValueError("candidate interval differs from requested actual trading day")
            provider = publish(root / "publication", document)
            attempt.update(status="succeeded", publicationId=provider.cache_revision())
        except Exception as exc:
            attempt.update(status="failed", errorType=type(exc).__name__, error=str(exc)[:2000])
        finally:
            attempt["finishedAt"] = datetime.now(TZ).isoformat()
            state["automaticTwoDayCandidate"] = consecutive(state["attempts"])
            atomic(state_path, state)
        return {"decision": attempt["status"], "state": state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    def deadline(signum, frame):
        raise TimeoutError("5400 second daily budget exhausted")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(5400)
    try:
        with redirect_stdout(sys.stderr):
            result = execute(ROOT, datetime.now(TZ), args.trigger, dry=args.dry_run)
        print(json.dumps(result, ensure_ascii=False))
        if result["decision"] == "failed":
            raise SystemExit(1)
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
