"""Deterministic train / validation / test window design for the RL ladder.

CR-052 records the tutor requirement: at least three years of training bars,
one to two years of held-out validation, a reserved test interval, everything
after 2015, and training that actually crosses rising, falling and sideways
markets instead of a single bull leg. Everything here is pure and needs no
torch, no real history and no network, so the gate itself is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_platform.rl.errors import RLInvalidSplit

# Earlier bars would need a session calendar we have not verified year by year.
HISTORY_FLOOR = date(2015, 1, 1)
MIN_TRAIN_DAYS = 3 * 365
MIN_VALIDATION_DAYS = 365
MAX_VALIDATION_DAYS = 2 * 365
# A one-year window holds ~240 sessions; below this the "validation" interval
# is a rounding error rather than held-out evidence.
MIN_VALIDATION_BARS = 180

# A regime is only credited when it is observed, not when it flashes for a bar.
REGIME_LOOKBACK = 63
REGIME_BAND = 0.15
MIN_REGIME_BARS = 20
REGIMES = ("bull", "bear", "sideways")

# Split attribute -> manifest key, so the recorded windows and the gate agree.
MANIFEST_KEYS = {
    "train_start": "trainStartDate",
    "train_end": "trainEndDate",
    "val_start": "valStartDate",
    "val_end": "valEndDate",
    "test_start": "testStartDate",
    "test_end": "testEndDate",
}


def _as_date(value: object, name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        value = value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise RLInvalidSplit(f"{name} 不是 ISO 日期：{value!r}") from exc
    if parsed.isoformat() != str(value):
        raise RLInvalidSplit(f"{name} 不是规范 ISO 日期：{value!r}")
    return parsed


@dataclass(frozen=True)
class Split:
    """Non-overlapping train / validation / test windows in closed date ranges.

    Windows are inclusive; ``__post_init__`` normalizes ``date | str`` inputs to
    ``date`` so ``repr`` and equality always describe the accepted windows.
    """

    train_start: date | str
    train_end: date | str
    val_start: date | str | None = None
    val_end: date | str | None = None
    test_start: date | str | None = None
    test_end: date | str | None = None

    def __post_init__(self) -> None:
        for name, key in MANIFEST_KEYS.items():
            object.__setattr__(self, name, _as_date(getattr(self, name), key))
        train_start, train_end = self.train_start, self.train_end
        val_start, val_end = self.val_start, self.val_end
        test_start, test_end = self.test_start, self.test_end

        for pair, label in (
            ((val_start, val_end), "验证"),
            ((test_start, test_end), "测试"),
        ):
            if (pair[0] is None) != (pair[1] is None):
                raise RLInvalidSplit(f"{label}区间起止必须同时提供")
        if test_start is not None and val_start is None:
            raise RLInvalidSplit("保留测试区间前必须先给出验证区间")
        if train_start is None or train_end is None:
            raise RLInvalidSplit("训练区间起止必须提供")
        if train_start < HISTORY_FLOOR:
            raise RLInvalidSplit(f"训练起点 {train_start} 早于已核对历史下限 {HISTORY_FLOOR}")
        if train_end <= train_start:
            raise RLInvalidSplit("训练终点必须晚于起点")
        if (train_end - train_start).days < MIN_TRAIN_DAYS:
            raise RLInvalidSplit(
                f"训练区间 {(train_end - train_start).days} 天不足 {MIN_TRAIN_DAYS} 天（三年）"
            )
        if val_start is not None and val_end is not None:
            span = (val_end - val_start).days
            if not MIN_VALIDATION_DAYS <= span <= MAX_VALIDATION_DAYS:
                raise RLInvalidSplit(
                    f"验证区间 {span} 天不在 1-2 年要求内"
                    f"（{MIN_VALIDATION_DAYS}-{MAX_VALIDATION_DAYS} 天）"
                )
        ordered = [train_start, train_end, val_start, val_end, test_start, test_end]
        previous = None
        for value in ordered:
            if value is None:
                continue
            if previous is not None and value <= previous:
                raise RLInvalidSplit("训练/验证/测试窗口必须按时间严格不重叠")
            previous = value

    @property
    def in_sample_end(self) -> date:
        """Last date that must never be scored as out-of-sample evidence."""
        return self.val_end or self.train_end

    def manifest_fields(self) -> dict[str, str]:
        """Manifest keys for the recorded windows; absent intervals are omitted."""
        return {
            MANIFEST_KEYS[name]: getattr(self, name).isoformat()
            for name in MANIFEST_KEYS
            if getattr(self, name) is not None
        }


def split_from_manifest(manifest) -> Split:
    try:
        return Split(
            train_start=manifest["trainStartDate"],
            train_end=manifest["trainEndDate"],
            val_start=manifest.get("valStartDate"),
            val_end=manifest.get("valEndDate"),
            test_start=manifest.get("testStartDate"),
            test_end=manifest.get("testEndDate"),
        )
    except KeyError as exc:
        raise RLInvalidSplit(f"manifest 缺少区间字段：{exc}") from exc


def in_sample_end(manifest) -> str:
    """Last ISO date that is still in-sample for this bundle ("" when unknown).

    Callers must use this instead of ``trainEndDate``: hyperparameters were
    selected on the validation window too, so scoring it as out-of-sample is
    leakage. Bundles trained before CR-052 fall back to the training end.
    """
    train_end = str(manifest.get("trainEndDate") or "")
    val_end = str(manifest.get("valEndDate") or "")
    return max(train_end, val_end)


def regime_labels(close: pd.Series) -> pd.Series:
    """Label each bar bull / bear / sideways from its trailing quarter momentum."""
    values = pd.Series(close).astype("float64").reset_index(drop=True)
    momentum = values.pct_change(periods=REGIME_LOOKBACK)
    labels = pd.Series("sideways", index=values.index, dtype="object")
    labels[momentum.isna()] = "warmup"
    labels[momentum >= REGIME_BAND] = "bull"
    labels[momentum <= -REGIME_BAND] = "bear"
    return labels


def regime_coverage(prices: pd.DataFrame) -> dict[str, int]:
    labels = regime_labels(prices["close"])
    counts = labels.value_counts()
    coverage = {name: int(counts.get(name, 0)) for name in REGIMES}
    coverage["warmup"] = int(counts.get("warmup", 0))
    return coverage


def require_regime_coverage(prices: pd.DataFrame) -> dict[str, int]:
    """Refuse a window that never crosses a bull, a bear and a sideways market."""
    if len(prices) < REGIME_LOOKBACK + MIN_REGIME_BARS:
        raise RLInvalidSplit(
            f"仅 {len(prices)} 根行情，无法判定牛/熊/震荡覆盖"
            f"（至少需要 {REGIME_LOOKBACK + MIN_REGIME_BARS} 根）"
        )
    coverage = regime_coverage(prices)
    missing = sorted(name for name in REGIMES if coverage[name] < MIN_REGIME_BARS)
    if missing:
        raise RLInvalidSplit(
            f"训练窗口未覆盖市场形态：缺少 {', '.join(missing)}"
            f"（观测 {coverage}，每类至少 {MIN_REGIME_BARS} 根）"
        )
    return coverage
