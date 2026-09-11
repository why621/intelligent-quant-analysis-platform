"""Validated current CSI300 snapshots; never a historical membership database."""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from quant_platform.models import Asset

SOURCE_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
    "file/autofile/cons/000300cons.xls"
)
INDEX_ID = "index:CSI:000300"
SHANGHAI = ZoneInfo("Asia/Shanghai")
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _code(value: object) -> str:
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{1,6}", text):
        raise ValueError("invalid security/index code")
    return text.zfill(6)


def _source_date(value: object) -> date:
    text = str(value).strip()
    if re.fullmatch(r"[0-9]{8}", text):
        return datetime.strptime(text, "%Y%m%d").date()
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        return date.fromisoformat(text)
    raise ValueError("invalid source date")


@dataclass(frozen=True)
class UniverseSnapshot:
    source_date: date
    retrieved_at: datetime
    source_sha256: str
    members: tuple[Asset, ...]

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include timezone")
        if self.source_date > self.retrieved_at.astimezone(SHANGHAI).date():
            raise ValueError("source date is in the future")
        if not re.fullmatch(r"[a-f0-9]{64}", self.source_sha256):
            raise ValueError("invalid source hash")
        if not isinstance(self.members, tuple) or len(self.members) != 300:
            raise ValueError("CSI300 requires exactly 300 members")
        symbols = set()
        for asset in self.members:
            if (not isinstance(asset, Asset) or asset.asset_type != "stock"
                    or not asset.active or not asset.name.strip()
                    or _code(asset.symbol) != asset.symbol):
                raise ValueError("invalid member")
            expected = "SSE" if asset.symbol.startswith("6") else "SZSE"
            if (asset.exchange not in {"SSE", "SZSE"} or asset.exchange != expected
                    or not asset.symbol.startswith(("6", "0", "3"))):
                raise ValueError("unsupported or inconsistent stock exchange")
            if asset.symbol in symbols:
                raise ValueError("duplicate member")
            symbols.add(asset.symbol)
        if self.members != tuple(sorted(self.members, key=lambda a: (a.exchange, a.symbol))):
            raise ValueError("members must be canonically sorted")

    def to_dict(self) -> dict[str, object]:
        body = {
            "schemaVersion": 1, "indexId": INDEX_ID, "membershipMode": "current_snapshot",
            "sourceUrl": SOURCE_URL, "sourceSha256": self.source_sha256,
            "sourceDate": self.source_date.isoformat(),
            "effectiveDate": None, "retrievedAt": self.retrieved_at.isoformat(),
            "historicalMembershipVerified": False,
            "members": [
                {"assetId": f"stock:{a.exchange}:{a.symbol}", "symbol": a.symbol,
                 "name": a.name, "exchange": a.exchange, "assetType": "stock", "active": True}
                for a in self.members
            ],
        }
        return {**body, "snapshotId": hashlib.sha256(_canonical(body)).hexdigest()}


def parse_constituents(frame: pd.DataFrame, *, retrieved_at: datetime,
                       source_sha256: str) -> UniverseSnapshot:
    """Validate meanings by column header, not SDK positional column renaming."""
    required = ("日期", "指数代码", "指数名称", "成分券代码", "成分券名称", "交易所")
    english = ("Date", "IndexCode", "IndexName", "ConstituentCode", "ConstituentName",
               "Exchange")
    columns = {}
    for label, suffix in zip(required, english, strict=True):
        matches = [
            c for c in frame.columns
            if re.sub(r"\s+", "", str(c)).replace("成份券", "成分券")
            in {label, label + suffix}
        ]
        if len(matches) != 1:
            raise ValueError(f"missing or ambiguous column: {label}")
        columns[label] = matches[0]
    if len(frame) != 300 or frame[list(columns.values())].isna().any().any():
        raise ValueError("expected 300 complete constituent rows")
    dates = {_source_date(value) for value in frame[columns["日期"]]}
    if len(dates) != 1:
        raise ValueError("mixed source dates")
    exchanges = {"上海证券交易所": "SSE", "深圳证券交易所": "SZSE"}
    assets = []
    for _, row in frame.iterrows():
        if (_code(row[columns["指数代码"]]) != "000300"
                or str(row[columns["指数名称"]]).strip() != "沪深300"):
            raise ValueError("wrong index identity")
        exchange = exchanges.get(str(row[columns["交易所"]]).strip())
        if exchange is None:
            raise ValueError("unknown exchange")
        assets.append(Asset(
            _code(row[columns["成分券代码"]]),
            str(row[columns["成分券名称"]]).strip(), "stock", exchange,
        ))
    return UniverseSnapshot(next(iter(dates)), retrieved_at, source_sha256,
                            tuple(sorted(assets, key=lambda a: (a.exchange, a.symbol))))


def snapshot_from_bytes(raw: bytes, *, retrieved_at: datetime) -> UniverseSnapshot:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("source file empty or oversized")
    frame = pd.read_excel(io.BytesIO(raw), dtype=str)
    return parse_constituents(frame, retrieved_at=retrieved_at,
                              source_sha256=hashlib.sha256(raw).hexdigest())


def save_snapshot(directory: Path, raw: bytes, snapshot: UniverseSnapshot) -> None:
    """New directory only; no live pointer, overwrite or production publication."""
    verified = snapshot_from_bytes(raw, retrieved_at=snapshot.retrieved_at)
    if verified != snapshot:
        raise ValueError("raw source and snapshot differ")
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "source.xls").write_bytes(raw)
    (directory / "snapshot.json").write_bytes(_canonical(snapshot.to_dict()) + b"\n")


def load_snapshot(directory: Path) -> UniverseSnapshot:
    manifest = directory / "snapshot.json"
    source = directory / "source.xls"
    if manifest.stat().st_size > MAX_SOURCE_BYTES or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("snapshot file oversized")
    document = json.loads(manifest.read_text(encoding="utf-8"))
    snapshot = snapshot_from_bytes(
        source.read_bytes(), retrieved_at=datetime.fromisoformat(document["retrievedAt"]))
    if document != snapshot.to_dict():
        raise ValueError("snapshot metadata or source has been modified")
    return snapshot
