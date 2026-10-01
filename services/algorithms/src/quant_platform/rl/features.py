"""Deterministic, causal feature pipeline shared by training and inference.

Every feature at bar *t* is a function of rows ``<= t`` only — rolling windows
never look ahead.

Two blocks, deliberately normalised in different ways:

* **momentum / microstructure** (short horizon) goes through a *rolling* z-score
  over the last ``Z_WINDOW`` rows. Rolling rather than expanding because expanding
  statistics are anchored to row 0 of whatever frame the caller passes, so the same
  calendar date would standardise differently in a training frame (row 0 = the 2015
  window start) and a serving frame (row 0 = the backtest start). A fitted scaler is
  still excluded — it is a training-time artefact that can smuggle future statistics
  into the transform.
* **regime / level** (long horizon) is *not* z-scored. CR-059 diagnosed why: a rolling
  z-score of a trend measure removes exactly the level that distinguishes a sustained
  decline from a sustained advance, so a 2022 grind and a 2015 rally end up
  statistically alike and the agent has no way to learn "be flat in a downtrend".
  These columns instead use a fixed analytic scale — vol-scaled trends and ratios —
  which keeps a persistent regime visible while staying frame-origin invariant.

Warm-up rows are left as ``NaN`` and carried by the caller.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 20
Z_WINDOW = 120

# Regime block lookbacks. ``REGIME_LOOKBACK`` is the long leg; the slope adds
# ``REGIME_SLOPE_STEP`` bars on top of it.
REGIME_LOOKBACK = 120
REGIME_SLOPE_STEP = 20
REGIME_BLOCK_LOOKBACK = REGIME_LOOKBACK + REGIME_SLOPE_STEP

MOMENTUM_COLUMNS: tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "ret_20",
    "vol_20",
    "sma_ratio_20",
    "hl_range",
    "gap",
    "mom_accel",
)

REGIME_COLUMNS: tuple[str, ...] = (
    "trend_120",
    "dd_from_peak_120",
    "vol_regime",
    "mom_60",
    "mom_120",
    "sma_slope_120",
)

FEATURE_COLUMNS: tuple[str, ...] = MOMENTUM_COLUMNS + REGIME_COLUMNS

# Bars needed before every feature column is populated: the momentum block needs its
# window plus the z-score's trailing history, the regime block needs its longest leg.
# Both come out at 140, so CR-059 did NOT lengthen the serving requirement.
MIN_WARMUP = max(DEFAULT_WINDOW + Z_WINDOW, REGIME_BLOCK_LOOKBACK)

# Volatility denominators are floored so a flat stretch cannot produce infinities.
_VOL_FLOOR = 1e-4
# A near-constant column (std ~1e-15 from float noise) would turn a z-score into
# noise/noise. The old guard only caught exactly 0.0; compare against a floor instead.
_STD_FLOOR = 1e-12
# Regime columns are analytic-scaled rather than z-scored, so bound the tail: real
# data stays well inside this, and it keeps a pathological flat stretch finite.
REGIME_CLIP = 6.0


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

    vol = ret_1.rolling(DEFAULT_WINDOW).std()
    scale = (vol * np.sqrt(REGIME_LOOKBACK)).clip(lower=_VOL_FLOOR)
    sma_long = close.rolling(REGIME_LOOKBACK).mean()
    feats["trend_120"] = np.log(close / sma_long) / scale
    feats["dd_from_peak_120"] = close / close.rolling(REGIME_LOOKBACK).max() - 1.0
    long_vol = ret_1.rolling(REGIME_LOOKBACK).std().clip(lower=_VOL_FLOOR)
    feats["vol_regime"] = np.log(vol.clip(lower=_VOL_FLOOR) / long_vol)
    feats["mom_60"] = np.log(close / close.shift(60)) / (vol * np.sqrt(60)).clip(lower=_VOL_FLOOR)
    feats["mom_120"] = np.log(close / close.shift(REGIME_LOOKBACK)) / scale
    feats["sma_slope_120"] = np.log(sma_long / sma_long.shift(REGIME_SLOPE_STEP)) / (
        vol * np.sqrt(REGIME_SLOPE_STEP)
    ).clip(lower=_VOL_FLOOR)
    return feats[list(FEATURE_COLUMNS)]


def rolling_zscore(features: pd.DataFrame, window: int = Z_WINDOW) -> np.ndarray:
    """Causal, frame-origin-independent normalisation over the trailing ``window``.

    Rows before ``MIN_WARMUP`` carry at least one ``NaN`` column (insufficient
    trailing history to standardise every feature) and are the caller's
    responsibility to skip or carry.
    """
    mean = features.rolling(window, min_periods=window).mean()
    std = features.rolling(window, min_periods=window).std()
    scaled = (features - mean) / std.where(std > _STD_FLOOR)
    return scaled.to_numpy(dtype=float)


def build_observations(prices: pd.DataFrame, window: int = DEFAULT_WINDOW) -> np.ndarray:
    """Compose the two blocks into the observation matrix the agents consume.

    The momentum block is rolling-z-scored; the regime block is passed through at its
    analytic scale so a persistent trend survives. Both are frame-origin invariant, so
    a training frame and a serving frame yield identical rows for the same date.
    """
    raw = build_features(prices, window=window)
    momentum = rolling_zscore(raw[list(MOMENTUM_COLUMNS)])
    regime = np.clip(raw[list(REGIME_COLUMNS)].to_numpy(dtype=float), -REGIME_CLIP, REGIME_CLIP)
    return np.hstack([momentum, regime])


def feature_signature(window: int = DEFAULT_WINDOW) -> str:
    """Stable hash binding the exact feature recipe, stored in model manifests."""
    payload = json.dumps(
        {
            "window": window,
            "z_window": Z_WINDOW,
            "columns": list(FEATURE_COLUMNS),
            "momentum_columns": list(MOMENTUM_COLUMNS),
            "regime_columns": list(REGIME_COLUMNS),
            "regime_lookback": REGIME_LOOKBACK,
            "regime_slope_step": REGIME_SLOPE_STEP,
            "min_warmup": MIN_WARMUP,
        },
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