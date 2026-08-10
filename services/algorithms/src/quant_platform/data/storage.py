"""Local, atomic stores for market data cached under ``data/processed``."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]
REQUIRED_OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
_SYMBOL_PATTERN = re.compile(r"\d{6}")
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


def _validate_symbol(symbol: str) -> None:
    if _SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError("symbol must be a six-digit string")


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


class OHLCVStore:
    """One CSV per asset, with schema validation and atomic replacement."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def _path(self, symbol: str) -> Path:
        _validate_symbol(symbol)
        return self._data_dir / f"{symbol}.csv"

    def has(self, symbol: str) -> bool:
        return self._path(symbol).exists()

    def load(self, symbol: str) -> pd.DataFrame:
        """Return a complete cached history, or an empty frame when absent."""
        path = self._path(symbol)
        if not path.exists():
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        return _normalise_ohlcv(pd.read_csv(path))

    def save(self, symbol: str, df: pd.DataFrame) -> None:
        """Validate, deduplicate, and atomically replace an asset CSV."""
        normalised = _normalise_ohlcv(df)
        if normalised.empty:
            return

        self._data_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(symbol)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix=f".{symbol}.",
                suffix=".tmp",
                dir=self._data_dir,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                normalised.to_csv(handle, index=False)
            temporary.replace(target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()


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
