#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch(url: str) -> tuple[int, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "regression-smoke/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read().decode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the regression stack")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    checks = [
        ("/", lambda body: "<div id=\"app\"></div>" in body),
        ("/api/health", lambda body: json.loads(body)["status"] == "ok"),
        ("/api/data/status", lambda body: json.loads(body)["source"] == "AkShare"),
        ("/api/assets?limit=3", lambda body: len(json.loads(body)["items"]) == 3),
        ("/api/strategies", lambda body: len(json.loads(body)["items"]) > 0),
    ]

    last_error: Exception | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            for path, validate in checks:
                status, content_type, body = fetch(f"{base_url}{path}")
                if status != 200 or not validate(body):
                    raise RuntimeError(
                        f"{path} failed: status={status}, content-type={content_type}"
                    )
            print(f"Regression smoke test passed: {len(checks)} checks at {base_url}")
            return
        except (KeyError, RuntimeError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt < args.attempts:
                time.sleep(2)

    raise SystemExit(f"Regression smoke test failed after {args.attempts} attempts: {last_error}")


if __name__ == "__main__":
    main()
