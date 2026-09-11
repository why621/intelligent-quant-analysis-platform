#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch(url: str, origin: str | None = None) -> tuple[int, str, str]:
    headers = {"User-Agent": "regression-smoke/1.0"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        if origin and response.headers.get("Access-Control-Allow-Origin") != origin:
            raise RuntimeError("API did not allow the requested browser origin")
        return (
            response.status,
            response.headers.get("Content-Type", ""),
            response.read().decode(),
        )


def verify_live_data(base_url: str, origin: str | None = None) -> None:
    def get(path):
        status, content_type, body = fetch(f"{base_url}{path}", origin)
        if status != 200 or "application/json" not in content_type:
            raise RuntimeError(f"{path}: expected JSON 200")
        return json.loads(body)

    state = get("/api/data/status")
    if state.get("status") != "ready" or any(
        state.get("components", {}).get(key, {}).get("status") != "ready"
        for key in ("history", "overview")
    ):
        raise RuntimeError(
            "real data is not ready; healthy containers are insufficient"
        )
    overview = get("/api/market/overview")
    traded = overview.get("tradeDate")
    from datetime import date

    date.fromisoformat(traded)
    if traded != state.get("latestTradeDate"):
        raise RuntimeError("overview/history trade dates differ")
    coverage = overview.get("coverage", {})
    if not coverage.get("total") or not coverage.get("priced"):
        raise RuntimeError("market snapshot has no validated coverage")
    history = get(f"/api/assets/510300/history?startDate={traded}&endDate={traded}")
    if not history.get("items") or history["items"][-1].get("date") != traded:
        raise RuntimeError("benchmark history does not cover the snapshot date")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the regression stack")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--strict-data", action="store_true")
    parser.add_argument(
        "--api-only", action="store_true", help="Backend-only host: do not require a frontend at /"
    )
    parser.add_argument(
        "--origin", help="Browser origin, e.g. https://why621.github.io"
    )
    parser.add_argument("--require-https", action="store_true")
    args = parser.parse_args()
    if args.require_https and not args.base_url.startswith("https://"):
        parser.error("GitHub Pages acceptance requires an HTTPS API endpoint")
    base_url = args.base_url.rstrip("/")
    checks = [
        ("/", lambda body: '<div id="app"></div>' in body),
        ("/api/health", lambda body: json.loads(body)["status"] == "ok"),
        ("/api/data/status", lambda body: json.loads(body)["source"] == "AkShare"),
        ("/api/assets?limit=3", lambda body: len(json.loads(body)["items"]) == 3),
        ("/api/strategies", lambda body: len(json.loads(body)["items"]) > 0),
    ]

    last_error: Exception | None = None
    if args.api_only:
        checks = [(path, validate) for path, validate in checks if path != "/"]
    for attempt in range(1, args.attempts + 1):
        try:
            for path, validate in checks:
                status, content_type, body = fetch(
                    f"{base_url}{path}",
                    args.origin if path.startswith("/api/") else None,
                )
                if status != 200 or not validate(body):
                    raise RuntimeError(
                        f"{path} failed: status={status}, content-type={content_type}"
                    )
            if args.strict_data:
                verify_live_data(base_url, args.origin)
            mode = (
                "strict live-data" if args.strict_data else "basic infrastructure only"
            )
            print(
                f"Regression smoke test passed ({mode}): {len(checks)} base checks at {base_url}"
            )
            return
        except (KeyError, RuntimeError, ValueError, urllib.error.URLError) as exc:
            if args.strict_data:
                raise SystemExit(f"Strict data acceptance failed: {exc}") from exc
            last_error = exc
            if attempt < args.attempts:
                time.sleep(2)

    raise SystemExit(
        f"Regression smoke test failed after {args.attempts} attempts: {last_error}"
    )


if __name__ == "__main__":
    main()
