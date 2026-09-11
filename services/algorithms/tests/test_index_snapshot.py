import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_platform.backtesting.engine import _compute_metrics
from quant_platform.data.index_snapshot import INDEX_ID, load_index, parse_index, save_index

START, END = date(2026, 9, 3), date(2026, 9, 7)


def raw(name="沪深300", rows=None):
    rows = (
        rows
        if rows is not None
        else [[d, "10", "11", "12", "9"] for d in ["2026-09-03", "2026-09-04", "2026-09-07"]]
    )
    return json.dumps(
        {"data": {"sh000300": {"qt": {"sh000300": ["1", name, "000300"]}, "day": rows}}}
    ).encode()


def test_explicit_identity_price_basis_and_unknown_volume():
    snapshot = parse_index(raw(), START, END)
    assert snapshot.to_dict()["assetId"] == INDEX_ID
    assert snapshot.to_dict()["returnBasis"] == "price_index"
    frame = snapshot.history(START, END)
    assert frame["volume"].isna().all() and frame["amount"].isna().all()
    assert frame["close"].tolist() == [11.0, 11.0, 11.0]


def test_etf_or_stock_name_cannot_impersonate_index():
    with pytest.raises(ValueError, match="identity"):
        parse_index(raw("沪深300ETF"), START, END)


@pytest.mark.parametrize(
    "rows",
    [
        [["2026-09-03", "10", "11", "12", "9"], ["2026-09-07", "10", "11", "12", "9"]],
        [["2026-09-03", "10", "11", "12", "9"]] * 3,
        [["2026-09-03", "nan", "11", "12", "9"]],
    ],
)
def test_bad_or_missing_index_prices_rejected(rows):
    with pytest.raises(ValueError):
        parse_index(raw(rows=rows), START, END)


def test_disk_hash_binding_and_interval(tmp_path):
    snapshot = save_index(raw(), START, END, tmp_path / "index")
    assert load_index(tmp_path / "index") == snapshot
    with pytest.raises(ValueError, match="range"):
        snapshot.history(date(2026, 9, 2), END)
    (tmp_path / "index/response.txt").write_bytes(raw().replace(b"12", b"13"))
    with pytest.raises(ValueError, match="hash"):
        load_index(tmp_path / "index")


def test_zero_strategy_returns_with_varying_index_has_beta_zero():
    dates = pd.date_range("2026-09-01", periods=5)
    strategy = pd.Series([100.0] * 5, index=dates)
    index = pd.Series([1.0, 1.02, 1.01, 1.04, 1.03], index=dates)
    metrics = _compute_metrics(strategy, index, 100.0)
    assert metrics.beta == 0.0 and metrics.alpha_pct == 0.0


def test_index_alpha_beta_matches_independent_covariance():
    dates = pd.date_range("2026-09-01", periods=5)
    strategy = pd.Series([100.0, 101.0, 103.0, 102.0, 104.0], index=dates)
    index = pd.Series([1.0, 1.02, 1.01, 1.04, 1.03], index=dates)
    metrics = _compute_metrics(strategy, index, 100.0)
    x, y = strategy.pct_change().dropna(), index.pct_change().dropna()
    beta = np.cov(x, y)[0, 1] / np.var(y, ddof=1)
    assert metrics.beta == pytest.approx(beta)
    assert metrics.alpha_pct == pytest.approx((x.mean() - beta * y.mean()) * 252 * 100)
