"""Bounded daily acquisition: separate acceptance and continuous operation ledgers."""

import argparse
import json
import signal
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_platform.data.calendar import latest_session
from quant_platform.data.coverage import digest
from quant_platform.data.index_snapshot import save_index
from quant_platform.data.publication import (
    PublishedProvider,
    checked_document,
    load_publication,
    publish,
)
from quant_platform.data.trading_events import load_events
from quant_platform.data.universe import load_snapshot

from tools.build_partial_publication import build_partial
from tools.collect_etf_candidate import collect
from tools.collect_history_universe import atomic, locked, run
from tools.maintain_trading_events import maintain, merge_confirmed
from tools.prepare_history_batch import worker_environment
from tools.verify_published_provider import verify

ROOT = Path("artifacts/cr025-daily-20260910")
CONTINUOUS_ROOT = Path("artifacts/continuous-daily")
BASE = Path("artifacts/cr024-publication-20260910")
UNIVERSE = Path("artifacts/cr012-universe-20260908")
TZ = ZoneInfo("Asia/Shanghai")


class DailyBudgetExceeded(RuntimeError):
    """Fatal whole-run deadline, distinct from recoverable provider I/O timeouts."""


def consecutive(attempts):
    days = sorted(
        {
            date.fromisoformat(a["targetDate"])
            for a in attempts
            if a["status"] == "succeeded" and a["trigger"] == "scheduled"
        }
    )
    return any(latest_session(b - timedelta(days=1)) == a for a, b in pairwise(days))


def pipeline(output, target, baseline_root=None):
    start = target - timedelta(days=365)
    universe = load_snapshot(UNIVERSE)
    errors = {}
    stages = {
        "stocks": lambda: run(
            universe,
            [a.symbol for a in universe.members],
            start,
            target,
            output / "stocks",
            events=load_events(Path("config/trading-events.json")),
            request_budget=1500,
            seconds_budget=3600,
        ),
        "etfs": lambda: collect(output / "etfs", start, target),
        "index": lambda: collect_index(output, start, target),
    }
    for name, collect_stage in stages.items():
        try:
            collect_stage()
        except DailyBudgetExceeded:
            raise
        except Exception as exc:
            errors[name] = type(exc).__name__
    baseline_root = baseline_root or BASE
    base = checked_document(baseline_root / "current.json")
    baseline = checked_document(baseline_root / "releases" / (base["publicationId"] + ".json"))
    previous = PublishedProvider(baseline)
    events, conflicts = merge_confirmed(
        previous.trading_events, load_events(Path("config/trading-events.json"))
    )
    # Reuse only proven unused request capacity, otherwise retain the conservative
    # stock reservation. ETF + index still reserve 135 + 2. No extra trial budget.
    capacity = 0
    manifest_path = output / "stocks" / "manifest.json"
    if manifest_path.exists():
        manifest = checked_document(manifest_path)
        if manifest.get("requestCountExact") is True and manifest.get("candidateId") == digest(
            {k: v for k, v in manifest.items() if k != "candidateId"}
        ):
            used = manifest.get("networkRequestsThisRun")
            if type(used) is int and 0 <= used <= 1500:
                capacity = max(0, min(1, 1637 - used - 135 - 2))
    maintenance = maintain(output, target, events, previous._assets, request_budget=capacity)
    if conflicts:
        maintenance["conflicts"] = sorted(set(maintenance["conflicts"] + conflicts))
        maintenance["state"] = "pending"
        atomic(output / "event-maintenance.json", maintenance)
    document = build_partial(
        output,
        start,
        target,
        baseline,
        UNIVERSE,
        output / "trading-events.json",
        errors,
    )
    atomic(output / "five-module.json", verify(PublishedProvider(document)))
    return document


def collect_index(output, start, target):
    result = subprocess.run(
        [sys.executable, "-m", "tools.index_probe"],
        input=json.dumps({"start": start.isoformat(), "end": target.isoformat()}),
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
        env=worker_environment(),
    )
    if len(result.stdout) > 4 * 1024 * 1024:
        raise ValueError("index worker output oversized")
    index = json.loads(result.stdout)
    save_index(index["raw"].encode("utf-8"), start, target, output / "index")
    atomic(output / "index" / "http-trace.json", index["httpTrace"])


def decision(state, target, baseline_end, *, mode="acceptance"):
    if mode not in {"acceptance", "continuous"}:
        raise ValueError("unknown run mode")
    attempts = state["attempts"]
    if mode == "acceptance" and consecutive(attempts):
        return "two_day_candidate_requires_scheduler_audit"
    if mode == "acceptance" and len(attempts) >= 4:
        return "budget_exhausted"
    if target <= baseline_end:
        return "waiting_new_day"
    if any(a["targetDate"] == target.isoformat() for a in attempts):
        return "already_attempted"
    return "eligible"


def execute(root, now, trigger, *, dry=False, build_candidate=pipeline, baseline=BASE, mode="acceptance"):
    if trigger not in {"manual", "scheduled"} or now.tzinfo is None:
        raise ValueError("explicit trigger and timezone required")
    now = now.astimezone(TZ)
    target = latest_session(now.date() - timedelta(days=1))
    baseline_provider = load_publication(baseline)
    state_path = root / "state.json"
    state = checked_document(state_path) if state_path.exists() else {"attempts": []}
    if mode == "continuous" and state_path.exists() and state.get("mode") != "continuous":
        raise ValueError("continuous mode requires its own ledger")
    status = decision(state, target, baseline_provider.end, mode=mode)
    if dry or status != "eligible":
        return {
            "decision": status,
            "targetDate": target.isoformat(),
            "dryRun": dry,
            "mode": mode,
            "maxRequestsPerAttempt": 1637,
        }
    root.mkdir(parents=True, exist_ok=True)
    with locked(root):
        state = checked_document(state_path) if state_path.exists() else {"attempts": []}
        if mode == "continuous":
            if state_path.exists() and state.get("mode") != "continuous":
                raise ValueError("continuous mode requires its own ledger")
            state["mode"] = "continuous"
            if shutil.disk_usage(root).free < 2 * 1024**3:
                raise RuntimeError("less than 2 GiB free; acquisition not started")
        status = decision(state, target, baseline_provider.end, mode=mode)
        if status != "eligible":
            return {"decision": status}
        output = root / target.isoformat()
        output.mkdir(exist_ok=False)
        attempt = {
            "targetDate": target.isoformat(),
            "startedAt": now.isoformat(),
            "trigger": trigger,
            "status": "running",
            "requestUpperBound": 1637,
        }
        state["attempts"].append(attempt)
        atomic(state_path, state)
        try:
            if not (root / "publication" / "current.json").exists():
                pointer = checked_document(baseline / "current.json")
                publish(
                    root / "publication",
                    checked_document(baseline / "releases" / (pointer["publicationId"] + ".json")),
                )
            source_root = root / "publication"
            if (
                build_candidate is pipeline
                and baseline_provider.end > load_publication(source_root).end
            ):
                source_root = baseline
            document = (
                pipeline(output, target, source_root)
                if build_candidate is pipeline
                else build_candidate(output, target)
            )
            candidate = PublishedProvider(document)
            if candidate.end != target or candidate.start != target - timedelta(days=365):
                raise ValueError("candidate interval differs from requested actual trading day")
            provider = publish(root / "publication", document)
            attempt.update(
                status="succeeded" if provider.availability["complete"] else "partial",
                publicationId=provider.cache_revision(),
                availability={k: v for k, v in provider.availability.items() if k != "assets"},
            )
        except Exception as exc:
            attempt.update(status="failed", errorType=type(exc).__name__, error=str(exc)[:2000])
        finally:
            attempt["finishedAt"] = datetime.now(TZ).isoformat()
            if mode == "acceptance":
                state["automaticTwoDayCandidate"] = consecutive(state["attempts"])
            atomic(state_path, state)
        return {"decision": attempt["status"], "state": state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=["acceptance", "continuous"], default="acceptance")
    args = parser.parse_args()

    def deadline(signum, frame):
        raise DailyBudgetExceeded("5400 second daily budget exhausted")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(5400)
    try:
        with redirect_stdout(sys.stderr):
            result = execute(CONTINUOUS_ROOT if args.mode == "continuous" else ROOT,
                             datetime.now(TZ), args.trigger, dry=args.dry_run, mode=args.mode)
        print(json.dumps(result, ensure_ascii=False))
        if result["decision"] == "failed":
            raise SystemExit(1)
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
