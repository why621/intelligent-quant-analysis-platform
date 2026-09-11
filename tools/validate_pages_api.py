"""Fail Pages builds with missing/HTTP/wrong-origin API configuration."""
import os
from urllib.parse import urlsplit


def validate(value: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("VITE_API_BASE_URL is not a valid URL") from exc
    if (
        value != value.strip()
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        or parsed.hostname.endswith(".github.io")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/api"
        or port == 0
    ):
        raise ValueError("Set VITE_API_BASE_URL to the verified HTTPS backend URL ending in /api")


if __name__ == "__main__":
    try:
        validate(os.environ.get("VITE_API_BASE_URL", ""))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Pages API URL syntax passed; certificate, CORS and live data still require smoke tests.")
