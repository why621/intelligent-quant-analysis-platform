"""Deterministic train / validation / test window design for the RL ladder.

CR-052 records the tutor requirement: at least three years of training bars,
one to two years of held-out validation, a reserved test interval, everything
after 2015, and training that actually crosses rising, falling and sideways
markets instead of a single bull leg. Everything here is pure and needs no
torch, no real history and no network, so the gate itself is unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_platform.rl.errors import RLInvalidSplit

# REQ-11 asks for bars from 2015 onwards; the session calendar has since CR-056
# been verified from 2014, so this floor is the requirement's own edge, not a gap.
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
class ValFold:
    """One held-out validation window used for checkpoint selection (CR-059).

    CR-059 replaced the single bull-market validation window with several folds,
    because a checkpoint chosen on a rising window is simply the one that stayed
    long, and the held-out test window was a decline.
    """

    start: date | str
    end: date | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _as_date(self.start, "foldStart"))
        object.__setattr__(self, "end", _as_date(self.end, "foldEnd"))
        if self.end <= self.start:
            raise RLInvalidSplit(f"验证折终点必须晚于起点：{self.start}..{self.end}")

    @property
    def span_days(self) -> int:
        return (self.end - self.start).days

    def manifest_fields(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def _as_fold(value: object) -> ValFold:
    if isinstance(value, ValFold):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return ValFold(value[0], value[1])
    if isinstance(value, Mapping) and {"start", "end"} <= set(value):
        return ValFold(value["start"], value["end"])
    raise RLInvalidSplit(
        f"验证折必须是 ValFold、(start, end) 二元组或 start/end 映射，实际 {value!r}"
    )


@dataclass(frozen=True)
class Split:
    """Non-overlapping train / validation / test windows in closed date ranges.

    Windows are inclusive; ``__post_init__`` normalizes ``date | str`` inputs to
    ``date`` so ``repr`` and equality always describe the accepted windows.

    ``val_folds`` carries the CR-059 multi-fold design. When given it is the single
    source of truth for the validation span: ``val_start``/``val_end`` are derived
    from its outer bounds so ``in_sample_end`` and the manifest stay consistent.
    """

    train_start: date | str
    train_end: date | str
    val_start: date | str | None = None
    val_end: date | str | None = None
    test_start: date | str | None = None
    test_end: date | str | None = None
    val_folds: tuple[ValFold, ...] = ()

    def __post_init__(self) -> None:
        folds = tuple(_as_fold(item) for item in self.val_folds or ())
        object.__setattr__(self, "val_folds", folds)
        if folds:
            object.__setattr__(self, "val_start", folds[0].start)
            object.__setattr__(self, "val_end", folds[-1].end)
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
        if val_start is not None and val_end is not None and not self.val_folds:
            span = (val_end - val_start).days
            if not MIN_VALIDATION_DAYS <= span <= MAX_VALIDATION_DAYS:
                raise RLInvalidSplit(
                    f"验证区间 {span} 天不在 1-2 年要求内"
                    f"（{MIN_VALIDATION_DAYS}-{MAX_VALIDATION_DAYS} 天）"
                )
        # Fold checks come first on purpose: val_start/val_end are derived from the
        # fold bounds, so the generic "windows must not overlap" message would
        # mask the specific cause (a fold inside training, or reaching into test).
        self._check_folds(train_end, test_start)
        ordered = [train_start, train_end, val_start, val_end, test_start, test_end]
        previous = None
        for value in ordered:
            if value is None:
                continue
            if previous is not None and value <= previous:
                raise RLInvalidSplit("训练/验证/测试窗口必须按时间严格不重叠")
            previous = value

    def _check_folds(self, train_end: date, test_start: date) -> None:
        """Folds tile the validation span: ordered, disjoint, inside the gap.

        The outer span is deliberately not checked against ``MAX_VALIDATION_DAYS``
        when folds exist — three one-year folds cover about 3.5 years by design;
        the per-fold bound is what keeps each one a meaningful held-out sample.
        """
        previous_end: date | None = None
        for index, fold in enumerate(self.val_folds, start=1):
            if not MIN_VALIDATION_DAYS <= fold.span_days <= MAX_VALIDATION_DAYS:
                raise RLInvalidSplit(
                    f"验证折 {index}（{fold.start}..{fold.end}）{fold.span_days} 天不在"
                    f" 1-2 年要求内（{MIN_VALIDATION_DAYS}-{MAX_VALIDATION_DAYS} 天）"
                )
            if previous_end is not None and fold.start <= previous_end:
                raise RLInvalidSplit(
                    f"验证折 {index} 起点 {fold.start} 与上一折终点 {previous_end} 重叠"
                )
            previous_end = fold.end
        if self.val_folds:
            if self.val_folds[0].start <= train_end:
                raise RLInvalidSplit(
                    f"验证折起点 {self.val_folds[0].start} 必须晚于训练终点 {train_end}"
                )
            if test_start is not None and self.val_folds[-1].end >= test_start:
                raise RLInvalidSplit(
                    f"验证折终点 {self.val_folds[-1].end} 必须早于测试起点 {test_start}"
                )

    @property
    def in_sample_end(self) -> date:
        """Last date that must never be scored as out-of-sample evidence."""
        return self.val_end or self.train_end

    def manifest_fields(self) -> dict[str, object]:
        """Manifest keys for the recorded windows; absent intervals are omitted."""
        fields: dict[str, object] = {
            MANIFEST_KEYS[name]: getattr(self, name).isoformat()
            for name in MANIFEST_KEYS
            if getattr(self, name) is not None
        }
        if self.val_folds:
            fields["valFolds"] = [fold.manifest_fields() for fold in self.val_folds]
        return fields


def split_from_manifest(manifest) -> Split:
    try:
        return Split(
            train_start=manifest["trainStartDate"],
            train_end=manifest["trainEndDate"],
            val_start=manifest.get("valStartDate"),
            val_end=manifest.get("valEndDate"),
            test_start=manifest.get("testStartDate"),
            test_end=manifest.get("testEndDate"),
            val_folds=tuple(manifest.get("valFolds") or ()),
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
