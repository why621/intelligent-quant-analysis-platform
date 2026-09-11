from unittest.mock import Mock

from tools.collect_etf_candidate import collect
from tools.test_prepare_history_batch import END, START, observation


def test_fixed_etf_scope_and_failed_source_stops(tmp_path):
    def failed(symbol, start, end):
        value = observation(symbol, start, end)
        value.update(error="offline synthetic failure", records=[])
        return value

    fetch = Mock(side_effect=failed)
    result = collect(
        tmp_path / "candidate", START, END, fetch=fetch, pause=lambda _: None
    )
    assert fetch.call_count == 3
    assert result["requestUpperBoundThisRun"] == 15
    assert not result["complete"] and not result["published"]
    assert all(e["asset"]["asset_type"] == "etf" for e in result["entries"])


def test_etf_full_scope_preserves_missing_rows(tmp_path):
    def missing(symbol, start, end):
        value = observation(symbol, start, end)
        if symbol == "513100":
            value["records"].pop()
        return value

    result = collect(
        tmp_path / "candidate", START, END, fetch=missing, pause=lambda _: None
    )
    assert len(result["entries"]) == 27
    assert result["requestUpperBoundThisRun"] == 135
    assert not result["complete"]
    assert [
        e["asset"]["symbol"]
        for e in result["entries"]
        if e["quality"]["status"] == "gaps"
    ] == ["513100"]
