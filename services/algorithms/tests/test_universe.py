"""Synthetic membership fixtures: not published CSI300 data."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from quant_platform.data import universe
from quant_platform.data.akshare_provider import AkShareMarketDataProvider

FETCHED = datetime(2026, 9, 8, 10, tzinfo=UTC)
HASH = hashlib.sha256(b"synthetic-source").hexdigest()


@pytest.fixture
def frame():
    return pd.DataFrame([{
        "日期Date": "20260907", "指数代码Index Code": "000300",
        "指数名称Index Name": "沪深300", "成分券代码Constituent Code": str(600000 + n),
        "成分券名称Constituent Name": f"测试股票{n}",
        "交易所Exchange": "上海证券交易所",
    } for n in range(300)])


def parse(frame, fetched=FETCHED):
    return universe.parse_constituents(frame, retrieved_at=fetched, source_sha256=HASH)


def test_snapshot_identity_schema_and_reproducibility(frame):
    frame.loc[0, "成分券代码Constituent Code"] = "1"
    frame.loc[0, "交易所Exchange"] = "深圳证券交易所"
    snapshot = parse(frame)
    assert snapshot.members[-1].symbol == "000001"
    assert snapshot.to_dict() == parse(frame.iloc[::-1]).to_dict()
    assert snapshot.to_dict()["effectiveDate"] is None
    assert snapshot.to_dict()["historicalMembershipVerified"] is False
    root = Path(__file__).resolve().parents[3]
    schema = yaml.safe_load((root / "packages/contracts/schemas/universe.yaml").read_text())
    Draft202012Validator(schema["UniverseSnapshot"], format_checker=FormatChecker()).validate(
        snapshot.to_dict())


@pytest.mark.parametrize("column,value", [
    ("日期Date", "20260909"), ("日期Date", "20260906"),
    ("日期Date", "not-a-date"), ("指数代码Index Code", "000905"),
    ("指数名称Index Name", "中证500"), ("成分券代码Constituent Code", "600001"),
    ("成分券代码Constituent Code", "600000.0"), ("成分券代码Constituent Code", "510300"),
    ("成分券名称Constituent Name", ""), ("成分券名称Constituent Name", None),
    ("交易所Exchange", "unknown"), ("交易所Exchange", "深圳证券交易所"),
])
def test_reject_invalid_rows(frame, column, value):
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        parse(frame)


def test_missing_ambiguous_columns_wrong_count_timezone(frame):
    for candidate in (frame.iloc[:-1], pd.concat([frame, frame.iloc[:1]]),
                      frame.drop(columns=["指数名称Index Name"]),
                      frame.assign(日期="20260907")):
        with pytest.raises(ValueError):
            parse(candidate)
    with pytest.raises(ValueError, match="timezone"):
        parse(frame, FETCHED.replace(tzinfo=None))


def test_official_header_variant_and_future_date(frame):
    renamed = frame.rename(columns=lambda c: c.replace("成分券", "成份券"))
    renamed["交易所英文名称Exchange(Eng)"] = "Shanghai Stock Exchange"
    assert parse(renamed).to_dict() == parse(frame).to_dict()
    duplicate = renamed.assign(成分券代码="600000")
    with pytest.raises(ValueError, match="ambiguous"):
        parse(duplicate)
    future = frame.copy()
    future["日期Date"] = "20260909"
    with pytest.raises(ValueError, match="future"):
        parse(future)


def test_roundtrip_raw_binding_and_no_overwrite(tmp_path, frame, monkeypatch):
    # Stub only XLS decoding; persistence and source hash checks are real.
    monkeypatch.setattr(universe.pd, "read_excel", lambda *a, **k: frame.copy())
    raw = b"synthetic-source"
    snapshot = universe.snapshot_from_bytes(raw, retrieved_at=FETCHED)
    directory = tmp_path / "snapshot"
    universe.save_snapshot(directory, raw, snapshot)
    assert universe.load_snapshot(directory) == snapshot
    with pytest.raises(FileExistsError):
        universe.save_snapshot(directory, raw, snapshot)
    (directory / "source.xls").write_bytes(b"modified")
    with pytest.raises(ValueError, match="modified"):
        universe.load_snapshot(directory)


@pytest.mark.parametrize("field,value", [
    ("sourceUrl", "https://invalid.example/"), ("sourceDate", "2026-09-06"),
    ("snapshotId", "0" * 64), ("historicalMembershipVerified", True),
])
def test_metadata_tampering_rejected(tmp_path, frame, monkeypatch, field, value):
    monkeypatch.setattr(universe.pd, "read_excel", lambda *a, **k: frame.copy())
    snapshot = universe.snapshot_from_bytes(b"synthetic-source", retrieved_at=FETCHED)
    directory = tmp_path / "snapshot"
    universe.save_snapshot(directory, b"synthetic-source", snapshot)
    manifest = directory / "snapshot.json"
    document = json.loads(manifest.read_text())
    document[field] = value
    manifest.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="modified"):
        universe.load_snapshot(directory)


def test_source_bound_and_explicit_universe_preserves_etfs(tmp_path, frame):
    for raw in (b"", b"x" * (universe.MAX_SOURCE_BYTES + 1)):
        with pytest.raises(ValueError):
            universe.snapshot_from_bytes(raw, retrieved_at=FETCHED)
    default = AkShareMarketDataProvider(tmp_path)
    before = {a.symbol for a in default.list_assets(asset_type="etf", limit=None)}
    expanded = AkShareMarketDataProvider(tmp_path, universe_snapshot=parse(frame))
    assert len(expanded.list_assets(asset_type="stock", limit=None)) == 300
    assert {a.symbol for a in expanded.list_assets(asset_type="etf", limit=None)} == before
    assert len(default.list_assets(limit=None)) == 50
    assert expanded.universe_snapshot.to_dict()["indexId"] == "index:CSI:000300"
