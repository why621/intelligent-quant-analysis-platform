"""Causal fixed-slot observations for the CR065 joint-portfolio research path.

The ten slots are NOT ten independent trading accounts. They contain concurrent
market features and the weights of one shared account. Training randomises slot
assignment; this lightweight MLP representation is not permutation equivariant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_platform.rl.features import (
    FEATURE_COLUMNS,
    build_observations,
    feature_signature,
    validate_history,
)

MAX_ASSETS = 10
MIN_ASSETS = 2
ACTION_SIZE = MAX_ASSETS + 1
SLOT_SIZE = len(FEATURE_COLUMNS) + 2  # market features, actual weight, active mask
OBSERVATION_SIZE = MAX_ASSETS * SLOT_SIZE + 1  # last element is actual cash weight
ENVIRONMENT_VERSION = "joint-portfolio-v1"


def observation_signature() -> str:
    layout = {
        "baseFeatures": feature_signature(),
        "maxAssets": MAX_ASSETS,
        "slotColumns": [*FEATURE_COLUMNS, "actualWeight", "activeMask"],
        "tail": "cashWeight",
        "action": "ten_nonnegative_scores_then_cash_normalized_after_hard_mask",
        "dates": "strict_identical_no_price_imputation",
    }
    return hashlib.sha256(json.dumps(layout, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class PortfolioPanel:
    symbols: tuple[str, ...]
    dates: pd.DatetimeIndex
    opens: np.ndarray
    closes: np.ndarray
    features: np.ndarray
    data_hashes: Mapping[str, str]

    def indices(self, symbols: Sequence[str]) -> np.ndarray:
        positions = {symbol: index for index, symbol in enumerate(self.symbols)}
        try:
            return np.asarray([positions[symbol] for symbol in symbols], dtype=int)
        except KeyError as exc:
            raise ValueError(f"unknown portfolio symbol: {exc.args[0]}") from exc


def prepare_panel(frames: Mapping[str, pd.DataFrame]) -> PortfolioPanel:
    """Validate a pool without silently dropping dates, assets or filling OHLCV.

    The training universe may be larger than ten; an episode samples at most ten.
    Callers must explicitly select a common covered window before calling this
    function. A missing bar is rejected rather than compressing the time axis.
    """
    if len(frames) < MIN_ASSETS:
        raise ValueError("joint portfolio requires at least two simultaneous assets")
    symbols = tuple(sorted(frames))
    if any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols):
        raise ValueError("portfolio symbols must be non-empty strings")
    dates = None
    opens, closes, observations = [], [], []
    hashes = {}
    for symbol in symbols:
        frame = frames[symbol].copy().reset_index(drop=True)
        validate_history(frame)
        current_dates = pd.DatetimeIndex(pd.to_datetime(frame["date"]))
        if current_dates.tz is not None or not current_dates.equals(current_dates.normalize()):
            raise ValueError(f"{symbol}: expected timezone-naive daily dates")
        if dates is None:
            dates = current_dates
        elif not dates.equals(current_dates):
            raise ValueError(f"{symbol}: portfolio dates differ; no silent alignment or filling")
        if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any() or (
            frame["low"] > frame[["open", "close", "high"]].min(axis=1)
        ).any():
            raise ValueError(f"{symbol}: inconsistent OHLC values")
        raw = frame[["date", "open", "high", "low", "close"]].copy()
        raw["date"] = current_dates.strftime("%Y-%m-%d")
        for column in ("open", "high", "low", "close"):
            raw[column] = raw[column].astype(float)
        hashes[symbol] = hashlib.sha256(
            raw.to_csv(index=False, float_format="%.17g", lineterminator="\n").encode()
        ).hexdigest()
        opens.append(frame["open"].to_numpy(dtype=float))
        closes.append(frame["close"].to_numpy(dtype=float))
        # Flat markets have zero-variance z-scores. Preserve the existing causal
        # convention, after enforcing the full warm-up, instead of fitting a scaler.
        observations.append(
            np.nan_to_num(build_observations(frame), nan=0.0, posinf=0.0, neginf=0.0)
        )
    return PortfolioPanel(
        symbols,
        dates,
        np.stack(opens, axis=1),
        np.stack(closes, axis=1),
        np.stack(observations, axis=1),
        hashes,
    )


def encode_observation(
    features: np.ndarray,
    quantities: Sequence[float],
    closes: Sequence[float],
    cash: float,
) -> np.ndarray:
    matrix = np.asarray(features, dtype=float)
    amounts = np.asarray(quantities, dtype=float) * np.asarray(closes, dtype=float)
    count = len(amounts)
    if not MIN_ASSETS <= count <= MAX_ASSETS or matrix.shape != (count, len(FEATURE_COLUMNS)):
        raise ValueError("invalid joint observation shape")
    if (
        not np.isfinite(matrix).all()
        or not np.isfinite(amounts).all()
        or (amounts < 0).any()
        or not np.isfinite(cash)
        or cash < 0
    ):
        raise ValueError("joint observation must contain finite nonnegative account values")
    equity = float(cash + amounts.sum())
    if equity <= 0:
        raise ValueError("joint account equity must be positive")
    slots = np.zeros((MAX_ASSETS, SLOT_SIZE), dtype=np.float32)
    slots[:count, : len(FEATURE_COLUMNS)] = matrix
    slots[:count, -2] = amounts / equity
    slots[:count, -1] = 1.0
    return np.concatenate((slots.reshape(-1), [cash / equity])).astype(np.float32)


def action_weights(action: Sequence[float], active_count: int) -> np.ndarray:
    """Project nonnegative scores onto active assets plus cash, exactly masking padding.

    All-zero scores explicitly mean 100% cash. This is a score parameterisation,
    not a claim that SB3's Gaussian density is a distribution over the simplex.
    """
    vector = np.asarray(action, dtype=float)
    if vector.shape != (ACTION_SIZE,) or not MIN_ASSETS <= active_count <= MAX_ASSETS:
        raise ValueError("joint action requires eleven scores and two to ten active assets")
    if not np.isfinite(vector).all() or (vector < 0).any() or (vector > 1).any():
        raise ValueError("joint action scores must be finite and between zero and one")
    weights = vector.copy()
    weights[active_count:MAX_ASSETS] = 0.0
    total = weights.sum()
    if total == 0:
        weights[-1] = 1.0
    else:
        weights /= total
    return weights
