"""Explicit, source-backed non-trading evidence; never infer suspension from a gap."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from quant_platform.data.coverage import digest


@dataclass(frozen=True)
class TradingEvent:
    asset_id: str
    start: date
    end: date
    reason: str
    source_url: str
    reviewed_on: date
    evidence_note: str

    def __post_init__(self):
        if not re.fullmatch(r"stock:(SSE|SZSE):[036][0-9]{5}", self.asset_id):
            raise ValueError("invalid event asset identity")
        market, symbol = self.asset_id.split(":")[1:]
        if (market == "SSE") != symbol.startswith("6"):
            raise ValueError("event exchange mismatch")
        if self.start > self.end or self.end > self.reviewed_on:
            raise ValueError("invalid event dates or unreviewed future event")
        if self.reason not in {"suspension", "pre_listing", "identity_change"}:
            raise ValueError("unsupported trading event")
        url = urlparse(self.source_url)
        host = url.hostname or ""
        if (
            url.scheme != "https"
            or url.username
            or url.password
            or url.port
            or not any(
                host == d or host.endswith("." + d)
                for d in ("sse.com.cn", "szse.cn", "cninfo.com.cn", "hkexnews.hk")
            )
        ):
            raise ValueError("event requires an official HTTPS disclosure source")
        if not self.evidence_note.strip():
            raise ValueError("event requires a reviewed evidence note")

    def to_dict(self):
        return {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in asdict(self).items()
        }

    @property
    def evidence_id(self):
        return digest(self.to_dict())


def validate_events(events):
    events = tuple(events)
    for i, event in enumerate(events):
        if not isinstance(event, TradingEvent):
            raise ValueError("invalid event type")
        for prior in events[:i]:
            if event.asset_id == prior.asset_id and max(event.start, prior.start) <= min(
                event.end, prior.end
            ):
                raise ValueError("overlapping or conflicting trading evidence")
    return tuple(sorted(events, key=lambda e: (e.asset_id, e.start)))


def load_events(path: Path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("event file oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or len(value) > 2000:
        raise ValueError("invalid event list")
    events = []
    for row in value:
        row = dict(row)
        for field in ("start", "end", "reviewed_on"):
            row[field] = date.fromisoformat(row[field])
        events.append(TradingEvent(**row))
    return validate_events(events)


def classify_sessions(events, asset_id, days):
    result = {}
    for event in validate_events(events):
        if event.asset_id == asset_id:
            for day in days:
                if event.start <= day <= event.end:
                    result[day] = event
    return result
