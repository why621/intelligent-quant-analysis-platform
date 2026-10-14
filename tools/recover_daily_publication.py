"""Offline recovery of the latest model-dependency gate failure; never acquires data.

Run inside a network-none container while the caller holds the cloud runner lock.
The original failed attempt remains intact. Promotion uses run_cloud_daily separately.
"""
import argparse
from datetime import date, datetime, timedelta

from quant_platform.data.coverage import digest
from quant_platform.data.publication import (
    PublishedProvider,
    checked_document,
    load_publication,
    publish,
)

from tools.build_partial_publication import build_partial
from tools.collect_history_universe import atomic, locked
from tools.daily_publication import BASE, CONTINUOUS_ROOT, TZ, UNIVERSE
from tools.verify_published_provider import verify


def recover(root, target, *, baseline=BASE, universe=UNIVERSE):
    with locked(root):
        state_path = root / "state.json"
        state = checked_document(state_path)
        if state.get("mode") != "continuous" or not state.get("attempts"):
            raise ValueError("continuous failure ledger required")
        original = state["attempts"][-1]
        if (original["targetDate"] != target.isoformat()
                or original["status"] != "failed"
                or original.get("errorType") != "RLDependenciesMissing"):
            raise ValueError("latest attempt must be the requested model-dependency failure")
        source = root / "publication"
        if load_publication(baseline).end > load_publication(source).end:
            source = baseline
        previous = load_publication(source)
        if previous.end >= target:
            raise ValueError("recovery must advance the baseline")
        pointer = checked_document(source / "current.json")
        document = checked_document(source / "releases" / (pointer["publicationId"] + ".json"))
        output = root / target.isoformat()
        start = target - timedelta(days=365)
        manifests = {}
        for stage in ("stocks", "etfs"):
            manifest = checked_document(output / stage / "manifest.json")
            if (manifest.get("candidateId") != digest({k: v for k, v in manifest.items() if k != "candidateId"})
                    or (manifest.get("startDate"), manifest.get("endDate")) != (start.isoformat(), target.isoformat())):
                raise ValueError("recovery source manifest hash/interval mismatch")
            manifests[stage] = manifest["candidateId"]
        # No pipeline()/maintain()/collect() call: reuse saved observations and events.
        candidate = build_partial(output, start, target, document, universe, output / "trading-events.json")
        provider = PublishedProvider(candidate)
        if provider.end != target or provider.start != start:
            raise ValueError("recovery candidate interval mismatch")
        gate = verify(provider)
        atomic(output / "five-module-recovery.json", gate)
        publish(root / "publication", candidate)
        stamp = datetime.now(TZ).isoformat()
        attempt = {
            "targetDate": target.isoformat(), "startedAt": stamp, "finishedAt": stamp,
            "trigger": "manual", "operation": "offline_recovery", "requestUpperBound": 0,
            "recoveryOf": original["startedAt"], "sourceCandidates": manifests,
            "baselinePublicationId": pointer["publicationId"],
            "status": "succeeded" if provider.availability["complete"] else "partial",
            "publicationId": provider.cache_revision(),
            "availability": {k: v for k, v in provider.availability.items() if k != "assets"},
        }
        state["attempts"].append(attempt)
        atomic(state_path, state)
        return attempt


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=date.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(recover(CONTINUOUS_ROOT, args.target), ensure_ascii=False))
