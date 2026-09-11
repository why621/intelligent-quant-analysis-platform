import copy
import json
from unittest.mock import patch

import pytest
from quant_platform.data.akshare_provider import _DEFAULT_UNIVERSE
from quant_platform.data.coverage import digest
from quant_platform.data.publication import PublishedProvider, load_publication, publish

from tools.test_prepare_history_batch import END, START, observation, snapshot


def document():
    universe = snapshot.__wrapped__().to_dict()
    symbols = [a["symbol"] for a in universe["members"]] + [
        a["symbol"] for a in _DEFAULT_UNIVERSE if a["asset_type"] == "etf"
    ]
    value = {
        "schemaVersion": 1,
        "startDate": START.isoformat(),
        "endDate": END.isoformat(),
        "createdAt": "2026-09-08T09:00:00+08:00",
        "universe": universe,
        "tradingEvents": [],
        "indexRaw": json.dumps(
            {
                "data": {
                    "sh000300": {
                        "qt": {"sh000300": ["1", "沪深300", "000300"]},
                        "day": [
                            [d, "10", "11", "12", "9"]
                            for d in ["2026-09-03", "2026-09-04", "2026-09-07"]
                        ],
                    }
                }
            }
        ),
        "sourceCandidates": ["a" * 64, "b" * 64],
        "histories": {s: observation(s)["records"] for s in symbols},
    }
    return {**value, "publicationId": digest(value)}


def rehash(value):
    value["publicationId"] = digest(
        {k: v for k, v in value.items() if k != "publicationId"}
    )
    return value


def test_incomplete_and_tamper_never_replace_current(tmp_path):
    good = document()
    publish(tmp_path, good)
    for tamper in ("hash", "missing"):
        bad = copy.deepcopy(good)
        bad["histories"]["600000"].pop()
        if tamper == "missing":
            rehash(bad)
        with pytest.raises(ValueError):
            publish(tmp_path, bad)
        assert load_publication(tmp_path).cache_revision() == good["publicationId"]


def test_atomic_failure_and_loaded_reader(tmp_path):
    good = document()
    reader = publish(tmp_path, good)
    new = copy.deepcopy(good)
    new["createdAt"] = "2026-09-08T10:00:00+08:00"
    rehash(new)
    with patch(
        "pathlib.Path.replace", side_effect=OSError("synthetic interrupted switch")
    ), pytest.raises(OSError):
        publish(tmp_path, new)
    assert load_publication(tmp_path).cache_revision() == good["publicationId"]
    publish(tmp_path, new)
    assert load_publication(tmp_path).cache_revision() == new["publicationId"]
    assert reader.cache_revision() == good["publicationId"]
    frame = reader.history("600000", START, END)
    frame.iloc[0, frame.columns.get_loc("close")] = 999
    assert reader.history("600000", START, END).iloc[0]["close"] == 11


def test_overview_and_coverage_api():
    from app import create_app

    provider = PublishedProvider(document())
    result = provider.market_overview()
    assert result["unchanged"] == 300
    assert result["coverage"] == {"total": 300, "priced": 300}
    assert result["turnoverCny"] is None
    client = create_app({"TESTING": True}, market_data_provider=provider).test_client()
    response = client.get("/api/data/coverage")
    assert response.status_code == 200
    assert response.json["dataContext"]["consistency"] == "published_snapshot"
    assert len(response.json["items"]) == 327
    assert (
        client.get("/api/market/overview").json["dataContext"]
        == response.json["dataContext"]
    )
    assert (
        client.get(
            "/api/data/coverage", headers={"X-Research-Version": "obsolete"}
        ).status_code
        == 409
    )
