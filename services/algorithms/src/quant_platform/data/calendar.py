"""Offline SSE/SZSE session calendar for the current MVP coverage (2025–2026).

Official SSE annual notices, checked 2026-09-07:
https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml
https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20251222_10802510.shtml
No guessed holiday rules outside these years. Extend annually before deployment.
This does not classify individual suspensions or overseas fund NAV sessions.
"""
from datetime import date, timedelta

_CLOSURES = {
    2025: [("01-01", "01-01"), ("01-28", "02-04"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("05-31", "06-02"), ("10-01", "10-08")],
    2026: [("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"),
           ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"),
           ("10-01", "10-07")],
}


class CalendarUnavailableError(ValueError):
    pass


def is_session(day: date) -> bool:
    if day.year not in _CLOSURES:
        raise CalendarUnavailableError(f"trading calendar not verified for {day.year}")
    if day.weekday() >= 5:
        return False
    month_day = day.strftime("%m-%d")
    return not any(start <= month_day <= end for start, end in _CLOSURES[day.year])


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
