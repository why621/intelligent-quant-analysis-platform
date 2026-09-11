"""Content-addressed complete local releases; readers never mutate or fetch data."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from quant_platform.data.akshare_provider import (
    _DEFAULT_UNIVERSE,
    AkShareMarketDataProvider,
    UpstreamUnavailableError,
)
from quant_platform.data.calendar import latest_session, sessions
from quant_platform.data.coverage import assess_history, canonical_bytes, digest
from quant_platform.data.index_snapshot import INDEX_ID, parse_index
from quant_platform.data.trading_events import TradingEvent, classify_sessions, validate_events
from quant_platform.data.universe import UniverseSnapshot
from quant_platform.models import Asset, DataStatus


def checked_document(path, limit=64 * 1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError("publication file oversized")
    return json.loads(path.read_text(encoding="utf-8"))


class PublishedProvider(AkShareMarketDataProvider):
    def __init__(self, document):
        value = copy.deepcopy(document)
        version = value.pop("publicationId")
        if digest(value) != version or value.get("schemaVersion") != 1:
            raise ValueError("publication hash or schema mismatch")
        self._version = version
        self._document = value
        self.start = date.fromisoformat(value["startDate"])
        self.end = date.fromisoformat(value["endDate"])
        universe = value["universe"]
        self.universe_snapshot = UniverseSnapshot(
            date.fromisoformat(universe["sourceDate"]),
            datetime.fromisoformat(universe["retrievedAt"]),
            universe["sourceSha256"],
            tuple(
                Asset(a["symbol"], a["name"], "stock", a["exchange"]) for a in universe["members"]
            ),
        )
        if self.universe_snapshot.to_dict() != universe:
            raise ValueError("publication universe mismatch")
        self.index_snapshot = parse_index(value["indexRaw"].encode("utf-8"), self.start, self.end)
        self.trading_events = validate_events(
            tuple(
                TradingEvent(
                    **{
                        k: date.fromisoformat(v) if k in {"start", "end", "reviewed_on"} else v
                        for k, v in row.items()
                    }
                )
                for row in value["tradingEvents"]
            )
        )
        self._assets = {a.symbol: a for a in self.universe_snapshot.members}
        self._assets.update(
            {a["symbol"]: Asset(**a) for a in _DEFAULT_UNIVERSE if a["asset_type"] == "etf"}
        )
        if set(value["histories"]) != set(self._assets) or len(self._assets) != 327:
            raise ValueError("publication requires exactly 300 constituents and 27 legacy ETFs")
        self._frames = {}
        self._coverage = []
        for symbol, asset in self._assets.items():
            frame = pd.DataFrame(value["histories"][symbol])
            quality = assess_history(
                frame,
                self.start,
                self.end,
                events=self.trading_events,
                asset_id=f"{asset.asset_type}:{asset.exchange}:{symbol}",
            )
            if quality["status"] not in {"complete", "complete_with_exceptions"}:
                raise ValueError("publication incomplete: " + symbol)
            frame["date"] = pd.to_datetime(frame["date"])
            self._frames[symbol] = frame
            self._coverage.append(
                {
                    "assetId": f"{asset.asset_type}:{asset.exchange}:{symbol}",
                    "symbol": symbol,
                    "startDate": self.start.isoformat(),
                    "endDate": self.end.isoformat(),
                    "quality": quality,
                }
            )
        self._overview = self._build_overview()

    @property
    def publication_context(self):
        return {
            "publicationDate": self.end.isoformat(),
            "universeVersion": self.universe_snapshot.to_dict()["snapshotId"],
            "dataVersion": self._version,
            "consistency": "published_snapshot",
        }

    def cache_revision(self):
        return self._version

    def status(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        fresh = self.end == latest_session(today - timedelta(days=1))
        return DataStatus(
            "ready" if fresh else "stale",
            "Tencent",
            327,
            self.end,
            datetime.fromisoformat(self._document["createdAt"]),
            "完整固定名单研究批次；存在幸存者偏差",
            components={
                "history": {"status": "ready", "message": "327资产覆盖验证通过"},
                "overview": {"status": "ready", "message": "同批次300成分日频概览"},
            },
        )

    @contextmanager
    def read_only_research(self, cutoff):
        if cutoff != self.end:
            raise UpstreamUnavailableError("publication cutoff mismatch")
        yield

    def history(self, symbol, start_date, end_date, adjust="qfq"):
        if symbol == INDEX_ID:
            return self.index_snapshot.history(start_date, end_date)
        if (
            adjust != "qfq"
            or symbol not in self._frames
            or start_date < self.start
            or end_date > self.end
            or start_date > end_date
        ):
            raise UpstreamUnavailableError("requested history outside immutable publication")
        frame = self._frames[symbol]
        selected = frame[
            (frame["date"] >= pd.Timestamp(start_date)) & (frame["date"] <= pd.Timestamp(end_date))
        ].copy(deep=True)
        if selected.empty:
            raise UpstreamUnavailableError("no tradable history in requested interval")
        return selected

    def nontrading_sessions(self, symbol, start, end):
        asset = self._assets[symbol]
        return set(
            classify_sessions(
                self.trading_events,
                f"{asset.asset_type}:{asset.exchange}:{symbol}",
                sessions(start, end),
            )
        )

    def update_daily(self, *args, **kwargs):
        raise RuntimeError("published readers cannot update; build and validate a new candidate")

    def coverage(self):
        return {
            "dataContext": self.publication_context,
            "memberCount": 300,
            "etfCount": 27,
            "items": copy.deepcopy(self._coverage),
        }

    def _build_overview(self):
        previous = sessions(self.start, self.end)[-2]
        counts = {"advancing": 0, "declining": 0, "unchanged": 0}
        turnover = 0.0
        suspended = 0
        priced = 0
        for asset in self.universe_snapshot.members:
            frame = self._frames[asset.symbol].set_index("date")
            if (
                pd.Timestamp(self.end) not in frame.index
                or pd.Timestamp(previous) not in frame.index
            ):
                suspended += 1
                continue
            current = frame.loc[pd.Timestamp(self.end)]
            prior = frame.loc[pd.Timestamp(previous)]
            change = current["close"] - prior["close"]
            counts["advancing" if change > 0 else "declining" if change < 0 else "unchanged"] += 1
            priced += 1
            if pd.isna(current["amount"]):
                turnover = None
            elif turnover is not None:
                turnover += float(current["amount"])
        # Missing current/prior bars are excluded from breadth, never labelled flat.
        if suspended:
            turnover = None
        index = self.index_snapshot.history(previous, self.end)
        return dict(
            tradeDate=self.end.isoformat(),
            scope="csi300_current_constituents",
            membershipMode="current_snapshot",
            dataContext=self.publication_context,
            **counts,
            suspended=suspended,
            limitUp=None,
            limitDown=None,
            turnoverCny=turnover,
            northboundNetCny=None,
            unavailableMetrics=["limitUp", "limitDown"]
            + (["turnoverCny"] if turnover is None else []),
            coverage={"total": 300, "priced": priced},
            indices=[
                {
                    "symbol": "000300",
                    "name": "沪深300价格指数",
                    "close": float(index.iloc[-1]["close"]),
                    "changePct": float(
                        (index.iloc[-1]["close"] / index.iloc[0]["close"] - 1) * 100
                    ),
                }
            ],
        )

    def market_overview(self):
        return copy.deepcopy(self._overview)


def load_publication(root):
    pointer = checked_document(root / "current.json", 4096)
    version = pointer["publicationId"]
    if not isinstance(version, str) or not re.fullmatch("[a-f0-9]{64}", version):
        raise ValueError("invalid publication pointer")
    path = root / "releases" / (version + ".json")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("publication path escapes root")
    value = checked_document(path)
    if value["publicationId"] != version:
        raise ValueError("publication pointer hash mismatch")
    return PublishedProvider(value)


def publish(root, document):
    provider = PublishedProvider(document)  # Entire candidate verified before touching pointer.
    root.mkdir(parents=True, exist_ok=True)
    releases = root / "releases"
    releases.mkdir(exist_ok=True)
    path = releases / (provider.cache_revision() + ".json")
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=releases, prefix="candidate-", delete=False
    ) as handle:
        handle.write(canonical_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())
        staged = Path(handle.name)
    try:
        try:
            os.link(staged, path)
        except FileExistsError:
            if checked_document(path) != document:
                raise ValueError("immutable release already differs") from None
    finally:
        staged.unlink(missing_ok=True)
    # A crash before pointer replacement leaves the previous release readable.
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=root, prefix="pointer-", delete=False
    ) as handle:
        handle.write(canonical_bytes({"publicationId": provider.cache_revision()}))
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        temporary.replace(root / "current.json")
    finally:
        temporary.unlink(missing_ok=True)
    return provider
