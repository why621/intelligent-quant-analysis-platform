import sqlite3
from datetime import date
from unittest.mock import patch

from quant_platform.data.storage import DataStatusStore


def test_missed_refresh_ages_component_statuses(tmp_path):
    store = DataStatusStore(tmp_path)
    store.save("ready", date(2025, 1, 3), "complete", components={
        "history": {"status": "ready", "message": "complete"},
        "overview": {"status": "ready", "message": "complete"},
    })
    with sqlite3.connect(tmp_path / "market_data.db") as conn:
        conn.execute("UPDATE data_status_sync SET updated_at = '2025-01-03T18:00:00+08:00'")
    with patch("quant_platform.data.storage.date") as clock:
        clock.today.return_value = date(2025, 1, 7)
        clock.fromisoformat = date.fromisoformat
        clock.fromordinal = date.fromordinal
        status = store.load(1)
    assert status.status == "stale"
    assert status.components["history"]["status"] == "stale"
    assert status.components["overview"]["status"] == "stale"
