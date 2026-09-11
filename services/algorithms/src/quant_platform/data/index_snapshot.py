"""Verified Tencent sh000300 price-index snapshots, separate from stock/ETF storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant_platform.data.calendar import sessions
from quant_platform.data.coverage import canonical_bytes, digest

INDEX_ID = "index:CSI:000300"
SOURCE_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"


@dataclass(frozen=True)
class IndexSnapshot:
    start: date
    end: date
    source_sha256: str
    records: tuple[tuple, ...]

    def to_dict(self):
        value = {
            "schemaVersion": 1,
            "assetId": INDEX_ID,
            "name": "沪深300价格指数",
            "source": "Tencent",
            "sourceUrl": SOURCE_URL,
            "sourceSymbol": "sh000300",
            "sourceSha256": self.source_sha256,
            "startDate": self.start.isoformat(),
            "endDate": self.end.isoformat(),
            "unit": "point",
            "returnBasis": "price_index",
            "adjust": "none",
            "records": [
                dict(zip(("date", "open", "high", "low", "close"), row, strict=True))
                for row in self.records
            ],
        }
        return {**value, "snapshotId": digest(value)}

    def history(self, start, end):
        if start < self.start or end > self.end:
            raise ValueError("index range is not covered by snapshot")
        frame = pd.DataFrame(self.to_dict()["records"])
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame[
            (frame["date"] >= pd.Timestamp(start)) & (frame["date"] <= pd.Timestamp(end))
        ].copy()
        # Unknown volume units are not mislabelled as shares/CNY.
        frame["volume"] = np.nan
        frame["amount"] = np.nan
        return frame


def parse_index(raw: bytes, start: date, end: date):
    if not raw or len(raw) > 2 * 1024 * 1024 or start > end or (end - start).days > 366:
        raise ValueError("invalid index snapshot bounds")
    text = raw.decode("utf-8")
    payload = json.loads(text[text.index("{") :])
    data = payload["data"]["sh000300"]
    quote = data["qt"]["sh000300"]
    if quote[1:3] != ["沪深300", "000300"]:
        raise ValueError("index identity mismatch")
    # For this verified index endpoint, unadjusted day is required; never fall back to qfqday.
    rows = data["day"]
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("invalid index rows")
    result = []
    for row in rows:
        observed = date.fromisoformat(row[0])
        if start <= observed <= end:
            opened, closed, high, low = map(float, row[1:5])
            prices = [opened, high, low, closed]
            if (
                not np.isfinite(prices).all()
                or min(prices) <= 0
                or high < max(prices)
                or low > min(prices)
            ):
                raise ValueError("invalid index prices")
            result.append((observed.isoformat(), opened, high, low, closed))
    expected = [d.isoformat() for d in sessions(start, end)]
    if not expected or [row[0] for row in result] != expected:
        raise ValueError("index has missing, duplicate or unordered trading dates")
    return IndexSnapshot(start, end, hashlib.sha256(raw).hexdigest(), tuple(result))


def save_index(raw, start, end, output):
    snapshot = parse_index(raw, start, end)
    output.mkdir(parents=True, exist_ok=False)
    (output / "response.txt").write_bytes(raw)
    (output / "snapshot.json").write_bytes(canonical_bytes(snapshot.to_dict()))
    return snapshot


def load_index(output: Path):
    manifest = json.loads((output / "snapshot.json").read_text())
    snapshot = parse_index(
        (output / "response.txt").read_bytes(),
        date.fromisoformat(manifest["startDate"]),
        date.fromisoformat(manifest["endDate"]),
    )
    if manifest != snapshot.to_dict():
        raise ValueError("index snapshot hash or provenance mismatch")
    return snapshot
