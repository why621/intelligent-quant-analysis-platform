"""Bounded, opt-in deep-history backfill into a research-only cache root.

CR-052: the tutor requires multi-year RL training windows, but the daily refresh
seeds an empty cache at ``today - 400 days`` and only ever extends forward, so
the live cache cannot reach 2015. This module is the explicit door for that work:
it writes a *separate* research root, never the published market cache, and it
refuses to start unless every requested year has a verified session calendar.

Running it pulls real history, which is slow and must be authorized per run;
``preflight`` is the cheap, network-free way to see what would be blocked.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from quant_platform.data.calendar import (
    CalendarUnavailableError,
    closure_basis,
    verified_years,
)


def unverified_years(start: date, end: date) -> list[int]:
    """Years in the range whose session calendar we cannot prove."""
    known = set(verified_years())
    return [year for year in range(start.year, end.year + 1) if year not in known]


def cross_validated_years(start: date, end: date) -> list[int]:
    """Years covered only by a cross-checked third-party calendar, not a notice."""
    return [
        year
        for year in range(start.year, end.year + 1)
        if closure_basis(year) == "cross-validated"
    ]


def preflight(start: date, end: date) -> dict[str, object]:
    """Report what a backfill would do *before* spending hours on network calls."""
    blocking = unverified_years(start, end)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "verifiedYears": [year for year in verified_years() if start.year <= year <= end.year],
        "unverifiedYears": blocking,
        "crossValidatedYears": cross_validated_years(start, end),
        "ready": not blocking,
        "reason": ""
        if not blocking
        else f"休市日历未核对年份：{blocking}，需先补官方公告证据",
    }


def backfill(
    root: Path,
    symbols: Sequence[str],
    start: date,
    end: date,
    *,
    adjust: str = "qfq",
) -> list[dict[str, object]]:
    """Fetch full-range history per symbol into ``root``; returns evidence rows.

    Whole-range fetching is not an optimisation: qfq re-anchors every bar after a
    dividend, so a partial refresh would mix adjustment bases.
    """
    from quant_platform.data.akshare_provider import (
        AkShareMarketDataProvider,
        _default_data_dir,
    )

    if not symbols:
        raise ValueError("必须显式给出至少一个 symbol，避免误拉全宇宙")
    resolved = Path(root).resolve()
    if resolved == _default_data_dir().resolve():
        raise ValueError("拒绝写入线上行情缓存，请使用独立研究历史目录")
    blocking = unverified_years(start, end)
    if blocking:
        raise CalendarUnavailableError(f"休市日历未核对年份：{blocking}")

    provider = AkShareMarketDataProvider(data_dir=resolved)
    provider.allow_research_calendar = True
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame = provider.history(symbol, start, end, adjust)  # type: ignore[arg-type]
        days = list(frame["date"].dt.date)
        rows.append(
            {
                "symbol": symbol,
                "adjust": adjust,
                "bars": int(len(days)),
                "firstDate": days[0].isoformat() if days else None,
                "lastDate": days[-1].isoformat() if days else None,
                "requestedStart": start.isoformat(),
                "requestedEnd": end.isoformat(),
            }
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按已核对休市日历回填深历史到独立研究目录（不触碰线上缓存）"
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--adjust", default="qfq", choices=("qfq", "hfq", "none"))
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--evidence-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = preflight(args.start, args.end)
    if args.preflight_only:
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ready"] else 2
    if not report["ready"]:
        print(json.dumps(report, ensure_ascii=False))
        return 2
    rows = backfill(args.root, args.symbol, args.start, args.end, adjust=args.adjust)
    payload = {"preflight": report, "symbols": rows}
    if args.evidence_out:
        Path(args.evidence_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.evidence_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
