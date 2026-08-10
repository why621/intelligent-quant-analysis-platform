"""CSV 行情存储：每个资产一个文件，路径 data/processed/{symbol}.csv。

初期使用 CSV，后续可平滑迁移到 SQLite。所有数据列统一为
date/open/high/low/close/volume/amount，日期升序且无重复。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume", "amount"]


class OHLCVStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def _path(self, symbol: str) -> Path:
        return self._data_dir / f"{symbol}.csv"

    def has(self, symbol: str) -> bool:
        return self._path(symbol).exists()

    def load(self, symbol: str) -> pd.DataFrame:
        """返回该资产的完整缓存行情；无缓存时返回空 DataFrame。"""
        path = self._path(symbol)
        if not path.exists():
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = pd.read_csv(path)
        for col in OHLCV_COLUMNS:
            if col not in df.columns:
                df[col] = 0.0 if col != "date" else None
        df["date"] = pd.to_datetime(df["date"])
        return df[OHLCV_COLUMNS].sort_values("date").drop_duplicates(subset="date")

    def save(self, symbol: str, df: pd.DataFrame) -> None:
        """把行情覆盖写入 CSV，自动去重并按日期排序。"""
        if df.empty:
            return
        self._data_dir.mkdir(parents=True, exist_ok=True)
        df = df[OHLCV_COLUMNS].sort_values("date").drop_duplicates(subset="date")
        df.to_csv(self._path(symbol), index=False)
