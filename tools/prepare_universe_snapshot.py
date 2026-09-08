"""One bounded official CSI300 download to a NEW ignored artifact directory.

No application update, production writes, retries, or stock-history requests.
Linux: run with the repo PYTHONPATH and project venv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from quant_platform.data.universe import (
    MAX_SOURCE_BYTES,
    SOURCE_URL,
    load_snapshot,
    save_snapshot,
    snapshot_from_bytes,
)


def download_source() -> bytes:
    with requests.Session() as session:
        session.trust_env = False
        with session.get(SOURCE_URL, timeout=(5, 10), allow_redirects=False,
                         stream=True) as response:
            if response.status_code != 200:
                raise ValueError(f"official source HTTP {response.status_code}")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    raise ValueError("official source file oversized")
                chunks.append(chunk)
            return b"".join(chunks)


def _deadline(_signal, _frame):
    raise TimeoutError("official snapshot operation exceeded 45 seconds")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input-download", type=Path,
                        help="Replay a captured download directory offline (zero HTTP requests)")
    args = parser.parse_args()
    artifact_root = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
    output = args.output.resolve()
    if not output.is_relative_to(artifact_root) or output == artifact_root or output.exists():
        parser.error("--output must be a NEW child directory of this repo's artifacts")
    if not hasattr(signal, "SIGALRM"):
        parser.error("Linux required for a hard operation deadline")
    signal.signal(signal.SIGALRM, _deadline)
    signal.alarm(45)
    try:
        if args.input_download:
            captured = args.input_download.resolve()
            if not captured.is_relative_to(artifact_root):
                parser.error("--input-download must be within artifacts")
            provenance = json.loads((captured / "download.json").read_text(encoding="utf-8"))
            source_file = captured / "source.xls"
            if source_file.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError("captured source file oversized")
            raw = source_file.read_bytes()
            if (provenance["sourceUrl"] != SOURCE_URL
                    or provenance["sourceSha256"] != hashlib.sha256(raw).hexdigest()):
                raise ValueError("captured source provenance mismatch")
            retrieved_at = datetime.fromisoformat(provenance["retrievedAt"])
            request_count = 0
        else:
            captured = output.with_name(output.name + "-download")
            if captured.exists():
                parser.error("download evidence directory already exists; replay it offline")
            retrieved_at = datetime.now(ZoneInfo("Asia/Shanghai"))
            raw = download_source()
            captured.mkdir(parents=True, exist_ok=False)
            (captured / "source.xls").write_bytes(raw)
            (captured / "download.json").write_text(json.dumps({
                "sourceUrl": SOURCE_URL, "retrievedAt": retrieved_at.isoformat(),
                "sourceSha256": hashlib.sha256(raw).hexdigest(),
            }), encoding="utf-8")
            request_count = 1
        snapshot = snapshot_from_bytes(raw, retrieved_at=retrieved_at)
        age = (retrieved_at.date() - snapshot.source_date).days
        if age > 7:
            raise ValueError(f"source date is {age} days old; manual freshness review required")
        save_snapshot(output, raw, snapshot)
        verified = load_snapshot(output)
        summary = {
            "scope": "official current membership only; not history coverage or production",
            "snapshotId": verified.to_dict()["snapshotId"],
            "sourceUrl": SOURCE_URL, "sourceSha256": verified.source_sha256,
            "sourceDate": verified.source_date.isoformat(),
            "retrievedAt": retrieved_at.isoformat(), "ageCalendarDays": age,
            "memberCount": len(verified.members),
            "uniqueSymbols": len({a.symbol for a in verified.members}),
            "exchangeCounts": dict(Counter(a.exchange for a in verified.members)),
            "historicalMembershipVerified": False, "effectiveDate": None,
            "requestCount": request_count, "output": str(output),
        }
        (output / "quality-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    main()
