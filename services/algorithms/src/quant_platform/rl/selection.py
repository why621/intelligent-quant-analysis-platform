"""Multiple-testing thresholds: put "best of N" on the same ruler as pure noise.

CR-059 measured background: the 36-run grid's best Sharpe on the 726-bar held-out
window was 0.761, while the formula below puts the expected best-of-12 noise Sharpe
at roughly 0.98 annualised. Without that ruler the ``picks.byTestSharpe`` table's
"+19..+54pp excess" reads as a result instead of a 12-draw extreme.

Formulas: the expected maximum is Bailey & Lopez de Prado's Deflated Sharpe Ratio
approximation for the order statistic of N standard normals, scaled by Lo (2002)'s
standard error of a Sharpe estimate. Two assumptions have to be stated because they
bound how the number may be used:

1. returns are i.i.d. normal -- real daily returns carry autocorrelation and fat
   tails, so this is an approximation;
2. trials are mutually independent -- our runs share one dataset and the four
   algorithms are correlated, so the true threshold is *higher* than computed here.
   Using this number as a gate is therefore conservative; it is never grounds for
   "it was not really that bad".

Pure functions with stdlib-only math: importable by the dependency-free test suite.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable

# Euler-Mascheroni, the weight the approximation places on the second quantile term.
EULER_GAMMA = 0.5772156649015329
TRADING_DAYS_PER_YEAR = 252

_NORMAL = statistics.NormalDist()


def expected_max_standard_errors(trials: int) -> float:
    """Expected maximum of ``trials`` i.i.d. standard normals, in sigma units.

    With a single trial there is no selection, so no inflation: 0.0.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if trials == 1:
        return 0.0
    first = _NORMAL.inv_cdf(1.0 - 1.0 / trials)
    second = _NORMAL.inv_cdf(1.0 - 1.0 / (trials * math.e))
    return (1.0 - EULER_GAMMA) * first + EULER_GAMMA * second


def sharpe_standard_error(sharpe: float, observations: int) -> float:
    """Lo (2002) standard error of a per-period Sharpe estimate."""
    if observations < 2:
        raise ValueError("observations must be >= 2")
    return math.sqrt((1.0 + 0.5 * sharpe * sharpe) / observations)


def noise_sharpe_threshold(
    trials: int,
    observations: int,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    sharpe: float = 0.0,
) -> float:
    """Annualised Sharpe a pure-noise strategy is expected to reach as best of ``trials``.

    ``observations`` is the number of per-period returns in the evaluated window.
    """
    scale = sharpe_standard_error(sharpe, observations)
    return expected_max_standard_errors(trials) * scale * math.sqrt(periods_per_year)


def annualize_sharpe(sharpe: float, *, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    return sharpe * math.sqrt(periods_per_year)


class MultipleTestingVerdict:
    """Outcome of comparing one observed Sharpe against the noise threshold."""

    __slots__ = ("observed", "threshold", "deflated_probability", "clears")

    def __init__(self, observed: float, threshold: float, deflated_probability: float) -> None:
        self.observed = observed
        self.threshold = threshold
        self.deflated_probability = deflated_probability
        self.clears = observed > threshold

    def as_dict(self) -> dict[str, float | bool]:
        return {
            "observedSharpe": round(self.observed, 6),
            "noiseSharpeThreshold": round(self.threshold, 6),
            "deflatedProbability": round(self.deflated_probability, 6),
            "clearsNoiseThreshold": self.clears,
        }


def deflate(
    sharpe: float,
    observations: int,
    trials: int,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> MultipleTestingVerdict:
    """Compare an annualised Sharpe against the best-of-``trials`` noise threshold.

    ``deflated_probability`` follows the paper's definition: the probability that the
    observed Sharpe exceeds the selection-inflated benchmark ``SR*``, i.e.
    ``Phi((SR_hat - SR*) / SE)``. Anything at or below 0.5 means the observation is
    indistinguishable from what picking the best of ``trials`` would produce from
    noise alone. It is *not* a p-value for "the strategy has edge", and the
    correlation between our trials makes it optimistic in the strategy's favour.
    """
    per_period = sharpe / math.sqrt(periods_per_year)
    threshold_per_period = expected_max_standard_errors(trials) * sharpe_standard_error(
        0.0, observations
    )
    error = sharpe_standard_error(per_period, observations)
    probability = _NORMAL.cdf((per_period - threshold_per_period) / error)
    threshold = annualize_sharpe(threshold_per_period, periods_per_year=periods_per_year)
    return MultipleTestingVerdict(sharpe, threshold, probability)


def min_track_record_length(
    sharpe: float,
    *,
    confidence: float = 0.95,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Periods needed before an observed annualised Sharpe is distinguishable from 0.

    Higher-moment corrections are omitted (skew/kurtosis are not recorded in the
    grid artifacts); treat the result as a floor, not a forecast.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if sharpe <= 0.0:
        return math.inf
    per_period = sharpe / math.sqrt(periods_per_year)
    z = _NORMAL.inv_cdf(confidence)
    return 1.0 + (z / per_period) ** 2


def annualized_sharpe_of(
    returns: Iterable[float], *, periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float:
    """Annualised Sharpe of a per-period return series (population moments).

    Returns 0.0 for a constant series rather than dividing by zero: a flat policy
    on a flat fold has no risk-adjusted content to select on.
    """
    values = [float(value) for value in returns]
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    variance = statistics.fmean([(value - mean) ** 2 for value in values])
    if variance <= 0.0:
        return 0.0
    return mean / math.sqrt(variance) * math.sqrt(periods_per_year)


def total_return_of(returns: Iterable[float]) -> float:
    """Sum of a per-period log-return series, i.e. the log return over the window."""
    return float(sum(float(value) for value in returns))


def median_fold_score(scores: Iterable[float]) -> float:
    """Selection statistic for CR-059: the median across validation folds.

    A median over three folds (one of which is a bear window) cannot be maximised by
    simply staying long, which is what a single bull-market validation window did.
    """
    values = [float(score) for score in scores]
    if not values:
        raise ValueError("median_fold_score needs at least one fold score")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("fold scores must be finite")
    return statistics.median(values)