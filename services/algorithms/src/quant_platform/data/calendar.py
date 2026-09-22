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
_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "calendar_closures.json"
_cache: tuple | None = None


class CalendarUnavailableError(ValueError):
    pass


def evidence_path() -> Path | None:
    configured = os.getenv(ENV_PATH)
    return Path(configured).expanduser() if configured else _DEFAULT_PATH


def parse_evidence(document) -> dict[int, list[tuple[str, str]]]:
    """Validate a closure table; every year must cite an official source."""
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise CalendarUnavailableError("calendar evidence requires schemaVersion=1")
    years = document.get("years")
    if not isinstance(years, dict):
        raise CalendarUnavailableError("calendar evidence requires a years object")
    table: dict[int, list[tuple[str, str]]] = {}
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
    return table


def _evidence_closures() -> dict[int, list[tuple[str, str]]]:
    global _cache
    path = evidence_path()
    if path is None or not path.is_file():
        return {}
    stamp = (str(path), path.stat().st_mtime_ns)
    if _cache is not None and _cache[0] == stamp:
        return _cache[1]
    try:
        table = parse_evidence(json.loads(path.read_text(encoding="utf-8")))
    except CalendarUnavailableError as exc:
        raise CalendarUnavailableError(f"{path}: {exc}") from exc
    _cache = (stamp, table)
    return table


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
