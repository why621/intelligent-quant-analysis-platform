"""Typed, dependency-free errors raised by the RL strategy runtime.

The HTTP backend maps ``code`` onto response error codes (see the handoff
notes); keeping them here means the algorithm module never imports Flask.
"""

from __future__ import annotations


class RLError(RuntimeError):
    """Base class for every RL runtime error."""

    code: str = "RL_ERROR"


class RLDependenciesMissing(RLError):
    """The optional ``[rl]`` extra (torch / stable-baselines3 / gymnasium) is absent."""

    code: str = "RL_DEPENDENCIES_MISSING"


class RLModelNotFound(RLError):
    """No trained model bundle exists for the requested ``modelRef``."""

    code: str = "RL_MODEL_NOT_FOUND"


class RLIncompatibleModel(RLError):
    """A bundle exists for ``modelRef`` but is not compatible with this strategy.

    Raised when the trained bundle's recorded ``algo`` differs from the
    requesting strategy, or its ``featureSignature`` no longer matches the
    feature recipe this build produces — i.e. a real "version mix" that must
    fail loudly instead of scoring a wrong/stale model and emitting garbage.
    """

    code: str = "RL_INCOMPATIBLE_MODEL"


class RLNotTrained(RLError):
    """A shared (untrained) strategy instance was asked to emit signals."""

    code: str = "RL_NOT_TRAINED"


class RLInSampleRequest(RLError):
    """Backtest range overlaps the training window, which would leak labels."""

    code: str = "RL_IN_SAMPLE_REQUEST"


class RLInsufficientHistory(RLError):
    """Not enough observed bars for feature warmup and one next-open execution."""

    code: str = "RL_INSUFFICIENT_HISTORY"
