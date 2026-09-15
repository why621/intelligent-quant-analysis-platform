"""Public, bounded diagnostics. Never expose raw upstream exception text."""


def failure_code(observation=None, quality=None, *, fallback="not_collected"):
    observation = observation or {}
    trace = observation.get("httpTrace") or []
    statuses = [t.get("status") for t in trace if isinstance(t, dict)]
    error = str(observation.get("error") or "")
    if 429 in statuses:
        return "rate_limited"
    if any(s in (401, 403) for s in statuses):
        return "access_denied"
    if any(isinstance(s, int) and s >= 500 for s in statuses):
        return "provider_unavailable"
    if "Timeout" in error:
        return "timeout"
    if any(e in error for e in ("Connection", "SSL", "RemoteDisconnected")):
        return "connection_failed"
    if error:
        return "invalid_response"
    state = (quality or {}).get("status")
    if state == "empty":
        return "empty_response"
    if state == "invalid":
        return "invalid_prices"
    if state == "gaps":
        return "missing_sessions"
    return "none" if state in {"complete", "complete_with_exceptions"} else fallback


RETRYABLE = {"rate_limited", "provider_unavailable", "timeout", "connection_failed"}
CODES = RETRYABLE | {
    "access_denied",
    "invalid_response",
    "empty_response",
    "invalid_prices",
    "missing_sessions",
    "not_collected",
    "none",
}
