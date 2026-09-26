"""Re-run the CR-054 audit: shipped closure table versus the official SSE notices.

Network-only research tool (it is not a pytest module). It re-fetches every notice
URL recorded in ``services/algorithms/data/calendar_closures.json``, re-parses the
announcement text into weekday closure sets, and compares them bidirectionally with
the table. Exit 0 only when each ``official-notice`` year agrees with its notices and
each ``cross-validated`` year differs exactly as its own record says it does.

    PYTHONUTF8=1 python services/algorithms/tests/golden/recheck_official_closures.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

TABLE = Path(__file__).resolve().parents[2] / "data" / "calendar_closures.json"
# 星期X in the notice text, 天 for 星期日 as written by some notices.
DATE = r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日（星期([一二三四五六日天])）"
SPAN = re.compile(DATE + "至" + DATE + "休市")
SINGLE = re.compile(DATE + "休市")
# Notices are cited inline, so a URL runs straight into Chinese punctuation:
# stop at the last ASCII path character or the next "fetch" asks for a 404.
URL = r"https://www\.sse\.com\.cn[A-Za-z0-9._/?=&%-]+"
CITATION = re.compile(
    r"《[^》]*》（上证公告〔(\d{4})〕\d+号，[^）]*发布）(" + URL + r")"
)
WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def article_text(html: str) -> str:
    body = re.search(r'<div class="allZoom">(.*?)</div>', html, re.S)
    text = re.sub(r"</p>|<br\s*/?>", "\n", body.group(1) if body else html)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(
        line.replace("&nbsp;", " ").replace("　", " ").strip()
        for line in text.splitlines()
        if line.strip()
    )


def pin(month: int, day: int, label: str, year: int, dated: bool) -> date:
    """Place a notice date in a year, checked against the weekday it states."""
    wanted = WEEKDAY[label]
    for candidate in ([year] if dated else [year, year - 1, year + 1]):
        try:
            found = date(candidate, month, day)
        except ValueError:
            continue
        if found.weekday() == wanted:
            return found
    raise AssertionError(f"{month}-{day} 星期{label} matches no year near {year}")


def notice_closures(text: str, stated_year: int) -> set[date]:
    """Weekday closures a single notice asserts, each filed under its own year."""
    days: set[date] = set()
    for line in text.splitlines():
        if "休市" not in line:
            continue
        # "另外，X月X日（星期Y）为周末休市" restates weekends; not evidence of a gap.
        for sentence in line.split("另外")[0].split("；"):
            spans = list(SPAN.finditer(sentence))
            for match in spans:
                start = pin(
                    int(match.group(2)), int(match.group(3)), match.group(4),
                    int(match.group(1) or stated_year), match.group(1) is not None,
                )
                end = pin(
                    int(match.group(6)), int(match.group(7)), match.group(8),
                    int(match.group(5) or stated_year), match.group(5) is not None,
                )
                while start <= end:
                    days.add(start)
                    start += timedelta(days=1)
            if not spans:
                for match in SINGLE.finditer(sentence):
                    days.add(
                        pin(
                            int(match.group(2)), int(match.group(3)), match.group(4),
                            int(match.group(1) or stated_year),
                            match.group(1) is not None,
                        )
                    )
    return {day for day in days if day.weekday() < 5}


def cited_notices(entry: dict) -> list[tuple[int, str]]:
    """(anchor year, URL) for every notice this year's record cites.

    The anchor is the 文号 year, because a temporary-arrangement notice has no year
    in its title (「…70周年纪念日休市安排的公告」) while its dates still need one.
    """

    text = json.dumps(entry, ensure_ascii=False)
    return sorted({(int(year), url) for year, url in CITATION.findall(text)})


def fetch_closures(url: str, anchor_year: int) -> set[date]:
    page = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    page.raise_for_status()
    page.encoding = "utf-8"
    title = re.search(r'<span id="searchTitle">(.*?)</span>', page.text, re.S)
    stated = re.search(r"(20\d{2})年", title.group(1) if title else "")
    return notice_closures(article_text(page.text), int(stated.group(1)) if stated else anchor_year)


def table_closures(year: int, ranges) -> set[date]:
    day, out = date(year, 1, 1), set()
    while day.year == year:
        month_day = day.strftime("%m-%d")
        if day.weekday() < 5 and any(s <= month_day <= e for s, e in ranges):
            out.add(day)
        day += timedelta(days=1)
    return out


def main() -> int:
    document = json.loads(TABLE.read_text(encoding="utf-8"))
    years = sorted(int(year) for year in document["years"])
    notices: dict[str, set[date]] = {}
    for year in years:
        for anchor, url in cited_notices(document["years"][str(year)]):
            notices.setdefault(url, fetch_closures(url, anchor))

    failures = []
    for year in years:
        entry = document["years"][str(year)]
        stated = {
            day
            for _, url in cited_notices(entry)
            for day in notices[url]
            if day.year == year
        }
        recorded = table_closures(year, [tuple(row) for row in entry["closures"]])
        notice_only = sorted(str(day) for day in stated - recorded)
        table_only = sorted(str(day) for day in recorded - stated)
        # A closure the notices state and the table lacks is always a defect. A
        # table-only day is tolerable only where that year's own record names it,
        # and only while the year is research grade.
        named = all(day in json.dumps(entry, ensure_ascii=False) for day in table_only)
        ok = not notice_only and named and (
            entry["basis"] == "cross-validated" or not table_only
        )
        print(
            f"{year} {entry['basis']:>15}: 公告 {len(stated):>2} 个休市工作日, "
            f"表内 {len(recorded):>2}, 公告有表无 {notice_only or '无'}, "
            f"表有公告无 {table_only or '无'}"
        )
        if not ok:
            failures.append(year)
    if failures:
        print(f"证据表与公告原文不再一致：{failures}；这些年份的 basis 必须降级", file=sys.stderr)
        return 1
    print(f"复算通过：{len(notices)} 份公告原文，{len(years)} 个年份")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
