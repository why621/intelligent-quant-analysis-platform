"""Offline SSE/SZSE session calendar with an evidence-backed extension path.

Official SSE annual notices, checked 2026-09-07:
https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml
https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml
No guessed holiday rules outside these years. Extend annually before deployment.
This does not classify individual suspensions or overseas fund NAV sessions.

Long-window RL research (CR-052) needs bars from years we have not hand-checked.
Rather than guess those holidays, ``QUANT_CALENDAR_EVIDENCE`` may point at a JSON
table recording each year's closure ranges *with the official source URL*. A year
without such a record stays unavailable, so an unverified window fails loudly
instead of silently producing a wrong expected-session set.

An entry states its ``basis``. ``official-notice`` (the default) means a human read
the exchange notice at ``source``. ``cross-validated`` is for years whose notice we
could not retrieve: it still cites ``source``, and additionally records where the
ranges came from and which independent comparisons matched them day-for-day, with
the date of the check. Such a year is research evidence, not a published one; a
bare, unexplained list of dates is refused.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

_CLOSURES = {
    2025: [("01-01", "01-01"), ("01-28", "02-04"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("05-31", "06-02"), ("10-01", "10-08")],
    2026: [("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"),
           ("10-01", "10-07")],
}

ENV_PATH = "QUANT_CALENDAR_EVIDENCE"
DEFAULT_EVIDENCE_PATH = Path(__file__).resolve().parents[3] / "data" / "calendar_closures.json"
_BASIS = ("official-notice", "cross-validated")
_cache: tuple | None = None


class CalendarUnavailableError(ValueError):
    pass


def evidence_path() -> Path | None:
    configured = os.getenv(ENV_PATH)
    return Path(configured).expanduser() if configured else DEFAULT_EVIDENCE_PATH


def parse_evidence(document) -> dict[int, list[tuple[str, str]]]:
    """Validate a closure table and return its year -> ranges mapping."""
    return _validate_evidence(document)[0]


def parse_evidence_basis(document) -> dict[int, str]:
    """Validate a closure table and return each year's basis."""
    return _validate_evidence(document)[1]


def _validate_evidence(document):
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise CalendarUnavailableError("calendar evidence requires schemaVersion=1")
    years = document.get("years")
    if not isinstance(years, dict):
        raise CalendarUnavailableError("calendar evidence requires a years object")
    table: dict[int, list[tuple[str, str]]] = {}
    basis: dict[int, str] = {}
    for key, entry in years.items():
        try:
            year = int(key)
        except (TypeError, ValueError) as exc:
            raise CalendarUnavailableError(f"calendar evidence year {key!r}") from exc
        if year in _CLOSURES:
            raise CalendarUnavailableError(
                f"{year} 已由官方公告核对，证据文件不得覆盖内置日历"
            )
        if not isinstance(entry, dict):
            raise CalendarUnavailableError(f"{year} evidence entry must be an object")
        source = entry.get("source")
        if not isinstance(source, str) or not source.startswith("https://"):
            raise CalendarUnavailableError(f"{year} 缺少官方 https 来源，拒绝采用")
        entry_basis = entry.get("basis", "official-notice")
        if entry_basis not in _BASIS:
            raise CalendarUnavailableError(f"{year} basis 未知：{entry_basis!r}")
        if entry_basis == "cross-validated":
            for field in ("derivedFrom", "checkedOn"):
                value = entry.get(field)
                if not isinstance(value, str) or not value:
                    raise CalendarUnavailableError(f"{year} 交叉核对缺少 {field}")
                if field == "checkedOn":
                    try:
                        date.fromisoformat(value)
                    except ValueError as exc:
                        raise CalendarUnavailableError(
                            f"{year} checkedOn 需为 YYYY-MM-DD"
                        ) from exc
            checks = entry.get("verifiedAgainst")
            if not isinstance(checks, list) or not checks or not all(
                isinstance(item, str) and item for item in checks
            ):
                raise CalendarUnavailableError(
                    f"{year} 非公告来源必须列出 verifiedAgainst 独立核对项"
                )
        ranges = entry.get("closures")
        if not isinstance(ranges, list) or not ranges:
            raise CalendarUnavailableError(f"{year} 缺少休市区间")
        checked: list[tuple[str, str]] = []
        for row in ranges:
            try:
                start, end = row
                date(year, int(start[:2]), int(start[3:]))
                date(year, int(end[:2]), int(end[3:]))
            except (TypeError, ValueError, IndexError) as exc:
                raise CalendarUnavailableError(f"{year} 休市区间非法：{row!r}") from exc
            if start > end:
                raise CalendarUnavailableError(f"{year} 休市区间倒置：{row!r}")
            checked.append((start, end))
        table[year] = checked
        basis[year] = entry_basis
    return table, basis


def _load_evidence():
    """Read the evidence table once per (path, mtime); a bad file fails loudly."""
    global _cache
    path = evidence_path()
    if path is None or not path.is_file():
        return {}, {}
    stamp = (str(path), path.stat().st_mtime_ns)
    if _cache is not None and _cache[0] == stamp:
        return _cache[1], _cache[2]
    try:
        table, basis = _validate_evidence(json.loads(path.read_text(encoding="utf-8")))
    except CalendarUnavailableError as exc:
        raise CalendarUnavailableError(f"{path}: {exc}") from exc
    _cache = (stamp, table, basis)
    return table, basis


def _evidence_closures() -> dict[int, list[tuple[str, str]]]:
    return _load_evidence()[0]


def closure_basis(year: int) -> str | None:
    """How a year's closure ranges were established, or None when unverified.

    ``cross-validated`` years are research-scope only: they were not read from the
    exchange's own annual notice, so the published data path must not rely on them.
    """
    if year in _CLOSURES:
        return "official-notice"
    return _load_evidence()[1].get(year)


def verified_years() -> list[int]:
    return sorted({*_CLOSURES, *_evidence_closures()})


def _closures(year: int) -> list[tuple[str, str]] | None:
    return _CLOSURES.get(year) or _evidence_closures().get(year)


def is_session(day: date) -> bool:
    ranges = _closures(day.year)
    if ranges is None:
        raise CalendarUnavailableError(f"trading calendar not verified for {day.year}")
    if day.weekday() >= 5:
        return False
    month_day = day.strftime("%m-%d")
    return not any(start <= month_day <= end for start, end in ranges)


def sessions(start: date, end: date) -> list[date]:
    result = []
    while start <= end:
        if is_session(start):
            result.append(start)
        start += timedelta(days=1)
    return result


def latest_session(day: date) -> date:
    while not is_session(day):
        day -= timedelta(days=1)
    return day
