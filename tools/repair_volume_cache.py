"""Back up, stage and optionally atomically repair legacy sz000 volume caches.

Run under maintenance (stop API/data writers) with a NEW backup directory.
Default is prepare-only. --apply is explicit and leaves the backup untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from quant_platform.data.akshare_provider import (
    _SZ000_VOLUME_VERSION,
    AkShareMarketDataProvider,
)
from quant_platform.data.calendar import sessions


def connect(path: Path, mode="ro"):
    return sqlite3.connect(path.resolve().as_uri() + f"?mode={mode}", uri=True)


def fingerprint(db):
    digest = hashlib.sha256()
    for line in db.iterdump():
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def repair(data_dir: Path, backup_dir: Path, *, apply=False, fetcher=None):
    source = data_dir / "market_data.db"
    if not source.is_file():
        raise ValueError("source database missing")
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / "market_data.original.db"
    stage_dir = backup_dir / "staged"
    stage_dir.mkdir()
    stage = stage_dir / "market_data.db"
    with closing(connect(source)) as original, closing(sqlite3.connect(backup)) as saved:
        original.backup(saved)
    with closing(connect(backup)) as saved, closing(sqlite3.connect(stage)) as staged:
        before = fingerprint(saved)
        saved.backup(staged)
        targets = saved.execute(
            "SELECT symbol, adjust, min(trade_date), max(trade_date) FROM ohlcv "
            "WHERE symbol LIKE '000%' AND NOT EXISTS (SELECT 1 FROM cache_metadata "
            "WHERE key = 'volume_schema:' || symbol || ':' || adjust AND value = ?) "
            "GROUP BY symbol, adjust ORDER BY symbol, adjust", (_SZ000_VOLUME_VERSION,),
        ).fetchall()
    provider = AkShareMarketDataProvider(stage_dir)
    fetch = fetcher or provider._fetch_tencent
    for symbol, adjust, first, last in targets:
        begin, end = date.fromisoformat(first), date.fromisoformat(last)
        frame = fetch(symbol, begin, end, adjust)
        expected = set(sessions(begin, end))
        if frame.empty or set(frame["date"].dt.date) != expected:
            raise ValueError(f"{symbol}: incomplete or unexpected trading dates")
        if frame["amount"].isna().any():
            raise ValueError(f"{symbol}: missing amount")
        provider._save_history_cache(symbol, frame, adjust)
        provider._load_history_cache(symbol, adjust)
        print(f"staged {symbol}/{adjust}: {len(frame)} rows {first}..{last}", flush=True)
    if not apply:
        return {"status": "prepared", "targets": len(targets), "backup": str(backup)}
    if not targets:
        return {"status": "already_verified", "targets": 0, "backup": str(backup)}
    with closing(connect(source, "rw")) as live:
        live.execute("ATTACH DATABASE ? AS repaired", (str(stage),))
        live.execute("BEGIN IMMEDIATE")
        try:
            if fingerprint(live) != before:
                raise ValueError("source changed after backup; refusing to apply")
            for symbol, adjust, _, _ in targets:
                live.execute("DELETE FROM main.ohlcv WHERE symbol=? AND adjust=?", (symbol, adjust))
                live.execute(
                    "INSERT INTO main.ohlcv SELECT * FROM repaired.ohlcv "
                    "WHERE symbol=? AND adjust=?", (symbol, adjust))
                live.execute(
                    "INSERT INTO main.cache_metadata(key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (f"volume_schema:{symbol}:{adjust}", _SZ000_VOLUME_VERSION))
            live.execute(
                "INSERT INTO main.cache_metadata(key,value) VALUES ('ohlcv_revision','1') "
                "ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
            live.commit()
        except BaseException:
            live.rollback()
            raise
    return {"status": "applied", "targets": len(targets), "backup": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(repair(args.data_dir.resolve(), args.backup_dir.resolve(), apply=args.apply), flush=True)


if __name__ == "__main__":
    main()
