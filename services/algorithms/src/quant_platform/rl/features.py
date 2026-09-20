"""Deterministic, causal feature pipeline shared by training and inference.

Every feature at bar *t* is a function of rows ``<= t`` only — rolling and
expanding windows never look ahead — so a live inference pass reproduces, bit
for bit, the observations the agent was trained on. Normalisation is an
*expanding* z-score rather than a fitted scaler for the same reason: a fitted
scaler is a training-time artefact that can smuggle future statistics into the
transform. Warm-up rows are left as ``NaN`` and carried by the caller.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 20
MIN_WARMUP = 20

FEATURE_COLUMNS: tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "ret_20",
    "vol_20",
    "sma_ratio_20",
    "hl_range",
    "gap",
    "mom_accel",
)


def build_features(prices: pd.DataFrame, window: int = DEFAULT_WINDOW) -> pd.DataFrame:
    """Return the raw (pre-normalisation) causal feature frame.

    ``prices`` must expose ``open`` and ``close`` columns in date order.
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing columns: {sorted(missing)}")

    close = prices["close"].astype(float)
    open_ = prices["open"].astype(float)
    high = prices["high"].astype(float)
    low = prices["low"].astype(float)

    ret_1 = close.pct_change(1)
    feats = pd.DataFrame(index=prices.index, dtype=float)
    feats["ret_1"] = ret_1
    feats["ret_5"] = close.pct_change(5)
    feats["ret_20"] = close.pct_change(20)
    feats["vol_20"] = ret_1.rolling(window).std()
    feats["sma_ratio_20"] = close / close.rolling(window).mean() - 1.0
    feats["hl_range"] = (high - low) / close
    feats["gap"] = open_ / close.shift(1) - 1.0
    feats["mom_accel"] = feats["ret_5"] - feats["ret_5"].shift(5)
    return feats[list(FEATURE_COLUMNS)]


def expanding_zscore(features: pd.DataFrame) -> np.ndarray:
    """Causal normalisation: subtract the expanding mean, divide by expanding std.

    The first ``MIN_WARMUP`` rows are NaN (insufficient history to standardise)
    and are the caller's responsibility to skip or carry.
    """
    mean = features.expanding(min_periods=MIN_WARMUP).mean()
    std = features.expanding(min_periods=MIN_WARMUP).std()
    scaled = (features - mean) / std.replace(0.0, np.nan)
    return scaled.to_numpy(dtype=float)


def feature_signature(window: int = DEFAULT_WINDOW) -> str:
    """Stable hash binding the exact feature recipe, stored in model manifests."""
    payload = json.dumps(
        {"window": window, "columns": list(FEATURE_COLUMNS), "min_warmup": MIN_WARMUP},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def validate_history(prices: pd.DataFrame, window: int = DEFAULT_WINDOW) -> None:
    """Check the observed sequence before reset/inference can index any bar."""
    from quant_platform.rl.errors import RLInsufficientHistory

    required = max(window, MIN_WARMUP) + 2
    if len(prices) < required:
        raise RLInsufficientHistory(
            f"强化学习至少需要 {required} 根有效行情（含预热和次日成交），实际 {len(prices)} 根"
        )
    if "date" not in prices:
        raise ValueError("RL prices require ordered dates")
    dates = pd.to_datetime(prices["date"], errors="raise")
    if dates.isna().any() or not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("RL prices must have unique ascending dates")
    values = prices[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("RL prices must be finite and positive")
