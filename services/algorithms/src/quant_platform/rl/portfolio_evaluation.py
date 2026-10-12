"""Chronological evaluation without fitting, for explicitly frozen candidates."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_platform.rl.portfolio_env import PortfolioEpisode
from quant_platform.rl.portfolio_features import prepare_panel
from quant_platform.rl.portfolio_policy import costs_from_metadata


def evaluate_portfolio(bundle, frames, *, start, end, baseline=None):
    """Validation/test replay. Caller freezes selection before requesting test data."""
    clipped = {
        s: f[pd.to_datetime(f.date) <= pd.Timestamp(end)].reset_index(drop=True)
        for s, f in frames.items()
    }
    panel = prepare_panel(clipped)
    first = int(panel.dates.searchsorted(pd.Timestamp(start)))
    episode = PortfolioEpisode(
        panel,
        asset_types=bundle.manifest["assetTypes"],
        trading_costs=costs_from_metadata(bundle.manifest["tradingCosts"]),
        random_subsets=False,
        random_start=False,
        episode_bars=len(panel.dates) - first - 1,
        band_pct=bundle.manifest.get("rebalanceBandPct", 0),
        min_trade_cny=bundle.manifest.get("minTradeCny", 0),
    )
    obs, info = episode.reset(options={"start_index": first})
    points = [info]
    turnover = 0.0
    while episode.bar < episode.end_bar:
        if baseline == "equal_weight_hold":
            action = np.zeros(11)
            if episode.bar == first:
                action[: len(panel.symbols)] = 1 / len(panel.symbols)
            else:
                # Preserve quantities exactly, without periodic rebalancing.
                episode.bar += 1
                info = episode.account()
                points.append(info)
                continue
        elif baseline == "ma_cross":
            bar = episode.bar
            short = panel.closes[bar - 7 : bar + 1].mean(axis=0)
            long = panel.closes[bar - 29 : bar + 1].mean(axis=0)
            active = short > long
            action = np.zeros(11)
            if active.any():
                action[: len(panel.symbols)] = active / active.sum()
            else:
                action[-1] = 1
        else:
            action, _ = bundle.model.predict(obs, deterministic=True)
        obs, _, _, _, info = episode.step(action)
        turnover += sum(f["amount_cny"] for f in info.get("fills", [])) / points[-1]["equity"]
        points.append(info)
    values = np.asarray([p["equity"] for p in points])
    returns = values[1:] / values[:-1] - 1
    metrics = {
        "returnPct": float((values[-1] / values[0] - 1) * 100),
        "maxDrawdownPct": float((1 - values / np.maximum.accumulate(values)).max() * 100),
        "sharpe": float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() else 0.0,
        "turnoverMultiple": float(turnover),
        "tradeCount": points[-1]["tradeCount"],
        "feesCny": points[-1]["cumulativeFees"],
        "slippageCny": points[-1]["cumulativeSlippage"],
    }
    for point in points:
        if not np.isfinite(point["equity"]) or point["cash"] < -1e-6:
            raise ValueError("invalid portfolio ledger")
        if abs(sum(point["weights"]) + point["cashWeight"] - 1) > 1e-8:
            raise ValueError("portfolio weights do not conserve capital")
    return {
        "startDate": points[0]["date"],
        "endDate": points[-1]["date"],
        "symbols": list(panel.symbols),
        "metrics": metrics,
        "accountCurve": points,
        "baseline": baseline,
        "costsIncluded": True,
    }
