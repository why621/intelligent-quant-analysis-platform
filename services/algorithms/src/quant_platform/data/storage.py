"""Local, atomic stores for market data cached under ``data/processed``."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from quant_platform.models import DataStatus

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]
REQUIRED_OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]

_MARKET_OVERVIEW_KEYS = {
    "tradeDate",
    "advancing",
    "declining",
    "unchanged",
    "limitUp",
    "limitDown",
    "turnoverCny",
    "northboundNetCny",
    "indices",
}


def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"missing required OHLCV columns: {', '.join(missing)}")

    result = df.copy()
    if "amount" not in result.columns:
        result["amount"] = float("nan")

    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in OHLCV_COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    invalid_required = result[REQUIRED_OHLCV_COLUMNS].isna().any(axis=1)
    if invalid_required.any():
        raise ValueError("OHLCV data contains invalid required values")

    return (
        result[OHLCV_COLUMNS]
        .sort_values("date")
        .drop_duplicates(subset="date", keep="last")
        .reset_index(drop=True)
    )


class DatabaseConnection:
    """创建短生命周期的 SQLite 连接，供不同进程安全共享同一数据库文件。"""

    @classmethod
    @contextmanager
    def connection(cls, data_dir: Path) -> Iterator[sqlite3.Connection]:
        db_path = Path(data_dir) / "market_data.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(db_path),
            timeout=5.0,
            check_same_thread=False,
        )
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            cls._init_db(conn)
            yield conn
        finally:
            conn.close()

    @classmethod
    def _init_db(cls, conn: sqlite3.Connection) -> None:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= 1:
            cls._migrate_v2(conn)
            return

        conn.execute("BEGIN IMMEDIATE")
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= 1:
                conn.commit()
                cls._migrate_v2(conn)
                return

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL,
                    PRIMARY KEY (symbol, trade_date)
                ) WITHOUT ROWID;
                """
            )

            status_exists = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'data_status_sync'
                """
            ).fetchone() is not None
            legacy_status = False
            if status_exists:
                columns = {
                    row[1]: row[3]
                    for row in conn.execute("PRAGMA table_info(data_status_sync)")
                }
                legacy_status = columns.get("updated_at") == 1
                if legacy_status:
                    conn.execute("ALTER TABLE data_status_sync RENAME TO data_status_sync_legacy")
                    status_exists = False

            if not status_exists:
                conn.execute(
                    """
                    CREATE TABLE data_status_sync (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        status TEXT NOT NULL,
                        updated_at TEXT,
                        latest_trade_date TEXT,
                        message TEXT
                    );
                    """
                )
                if legacy_status:
                    conn.execute(
                        """
                        INSERT INTO data_status_sync
                            (id, status, updated_at, latest_trade_date, message)
                        SELECT id, status, updated_at, latest_trade_date, message
                        FROM data_status_sync_legacy
                        """
                    )
                    conn.execute(
                        """
                        UPDATE data_status_sync
                        SET updated_at = NULL
                        WHERE status = 'updating'
                          AND latest_trade_date IS NULL
                          AND message = '初始化状态'
                        """
                    )
                    conn.execute("DROP TABLE data_status_sync_legacy")

            conn.execute(
                """
                INSERT OR IGNORE INTO data_status_sync
                    (id, status, updated_at, latest_trade_date, message)
                VALUES (1, 'updating', NULL, NULL, '初始化状态')
                """
            )
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        cls._migrate_v2(conn)

    @classmethod
    def _migrate_v2(cls, conn: sqlite3.Connection) -> None:
        """Separate adjusted price caches and add migration metadata."""
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= 2:
            return

        conn.execute("BEGIN IMMEDIATE")
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= 2:
                conn.commit()
                return

            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(ohlcv)")
            }
            if "adjust" not in columns:
                conn.execute("ALTER TABLE ohlcv RENAME TO ohlcv_v1")
                conn.execute(
                    """
                    CREATE TABLE ohlcv (
                        symbol TEXT NOT NULL,
                        adjust TEXT NOT NULL,
                        trade_date TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,
                        amount REAL,
                        PRIMARY KEY (symbol, adjust, trade_date)
                    ) WITHOUT ROWID;
                    """
                )
                conn.execute(
                    """
                    INSERT INTO ohlcv
                        (symbol, adjust, trade_date, open, high, low, close, volume, amount)
                    SELECT symbol, 'qfq', trade_date, open, high, low, close, volume, amount
                    FROM ohlcv_v1
                    """
                )
                conn.execute("DROP TABLE ohlcv_v1")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) WITHOUT ROWID;
                """
            )
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


class OHLCVStore:
    """Store market data in SQLite for cross-process concurrency."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._migrate_legacy_csvs()

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def has(self, symbol: str, adjust: str = "qfq") -> bool:
        if not symbol.isdigit() or len(symbol) != 6:
            return False
        self._validate_adjust(adjust)
        with DatabaseConnection.connection(self._data_dir) as conn:
            cur = conn.execute(
                "SELECT 1 FROM ohlcv WHERE symbol = ? AND adjust = ? LIMIT 1",
                (symbol, adjust),
            )
            return cur.fetchone() is not None

    def load(self, symbol: str, adjust: str = "qfq") -> pd.DataFrame:
        """Return a complete cached history, or an empty frame when absent."""
        if not symbol.isdigit() or len(symbol) != 6:
            raise ValueError("symbol must be a six-digit string")

        self._validate_adjust(adjust)
        with DatabaseConnection.connection(self._data_dir) as conn:
            df = pd.read_sql_query(
                """
                SELECT trade_date AS date, open, high, low, close, volume, amount
                FROM ohlcv
                WHERE symbol = ? AND adjust = ?
                ORDER BY trade_date ASC
                """,
                conn,
                params=(symbol, adjust),
            )
        if df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        return _normalise_ohlcv(df)

    def save(self, symbol: str, df: pd.DataFrame, adjust: str = "qfq") -> None:
        """Validate, deduplicate, and atomically save asset data to SQLite."""
        if not symbol.isdigit() or len(symbol) != 6:
            raise ValueError("symbol must be a six-digit string")

        self._validate_adjust(adjust)
        normalised = _normalise_ohlcv(df)
        if normalised.empty:
            return

        with DatabaseConnection.connection(self._data_dir) as conn:
            self._upsert(conn, symbol, adjust, normalised)
            conn.commit()

    @staticmethod
    def _validate_adjust(adjust: str) -> None:
        if adjust not in {"qfq", "hfq", "none"}:
            raise ValueError("adjust must be one of: qfq, hfq, none")

    @staticmethod
    def _upsert(
        conn: sqlite3.Connection,
        symbol: str,
        adjust: str,
        normalised: pd.DataFrame,
    ) -> None:
        df_save = normalised.copy()
        df_save["symbol"] = symbol
        df_save["adjust"] = adjust
        df_save["trade_date"] = df_save["date"].dt.strftime("%Y-%m-%d")
        records = df_save[
            ["symbol", "adjust", "trade_date", "open", "high", "low", "close",
             "volume", "amount"]
        ].to_dict(orient="records")
        conn.executemany(
            """
            INSERT INTO ohlcv
                (symbol, adjust, trade_date, open, high, low, close, volume, amount)
            VALUES (:symbol, :adjust, :trade_date, :open, :high, :low, :close,
                    :volume, :amount)
            ON CONFLICT(symbol, adjust, trade_date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                amount=excluded.amount;
            """,
            records,
        )

    def _migrate_legacy_csvs(self) -> None:
        legacy_paths = sorted(
            path for path in self._data_dir.glob("*.csv")
            if path.stem.isdigit() and len(path.stem) == 6
        )
        with DatabaseConnection.connection(self._data_dir) as conn:
            conn.execute("BEGIN IMMEDIATE")
            migrated = conn.execute(
                "SELECT value FROM cache_metadata WHERE key = 'legacy_csv_migrated'"
            ).fetchone()
            if migrated is not None:
                conn.commit()
                return

            migration_failed = False
            for path in legacy_paths:
                try:
                    normalised = _normalise_ohlcv(pd.read_csv(path))
                except (OSError, UnicodeError, ValueError):
                    migration_failed = True
                    continue
                if not normalised.empty:
                    self._upsert(conn, path.stem, "qfq", normalised)

            if not migration_failed:
                conn.execute(
                    """
                    INSERT INTO cache_metadata (key, value)
                    VALUES ('legacy_csv_migrated', '1')
                    """
                )
            conn.commit()


class MarketOverviewStore:
    """Single JSON snapshot used by HTTP requests between daily refreshes."""

    def __init__(self, data_dir: Path) -> None:
        self._path = Path(data_dir) / "market_overview.json"

    def load(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or not _MARKET_OVERVIEW_KEYS.issubset(value):
            return None
        if not isinstance(value.get("tradeDate"), str):
            return None
        return value

    def save(self, overview: dict[str, object]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".market_overview.",
                suffix=".tmp",
                dir=self._path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(overview, handle, ensure_ascii=False, allow_nan=False)
            temporary.replace(self._path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


def _has_completed_weekday_since(updated_date: date, today: date) -> bool:
    """Return whether an expected weekday refresh has been missed."""
    return any(
        date.fromordinal(day).weekday() < 5
        for day in range(updated_date.toordinal() + 1, today.toordinal())
    )


class DataStatusStore:
    """Persist and derive daily refresh status across processes."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    def load(self, fallback_asset_count: int) -> DataStatus:
        with DatabaseConnection.connection(self._data_dir) as conn:
            conn.execute("BEGIN")
            row = conn.execute("SELECT * FROM data_status_sync WHERE id = 1").fetchone()
            component_row = conn.execute(
                "SELECT value FROM cache_metadata WHERE key = 'data_components'"
            ).fetchone()
        components = json.loads(component_row[0]) if component_row else {}

        if row is None:
            raise RuntimeError("data status row is missing")

        updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
        latest_date = (
            date.fromisoformat(row["latest_trade_date"])
            if row["latest_trade_date"]
            else None
        )
        stored_status = row["status"]

        if updated_at and _has_completed_weekday_since(updated_at.date(), date.today()):
            if stored_status in ("ready", "updating"):
                stored_status = "stale" if latest_date else "failed"
            for component in components.values():
                if component.get("status") in ("ready", "updating"):
                    component["status"] = "stale"
                    component["message"] = "未完成预期的日更，请检查更新任务"

        return DataStatus(
            status=stored_status,  # type: ignore[arg-type]
            source="AkShare",
            asset_count=fallback_asset_count,
            latest_trade_date=latest_date,
            updated_at=updated_at,
            message=row["message"],
            components=components,
        )

    def save(
        self, status: str, latest_trade_date: date | None, message: str | None,
        *, components: dict[str, object] | None = None,
    ) -> None:
        latest_date = latest_trade_date.isoformat() if latest_trade_date else None
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        with DatabaseConnection.connection(self._data_dir) as conn:
            conn.execute(
                """
                UPDATE data_status_sync
                SET status = ?, updated_at = ?, latest_trade_date = ?, message = ?
                WHERE id = 1
                """,
                (status, now, latest_date, message),
            )
            conn.execute(
                """
                INSERT INTO cache_metadata (key, value) VALUES ('data_components', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (json.dumps(components or {}, ensure_ascii=False, allow_nan=False),),
            )
            conn.commit()
