"""Single-agent reinforcement-learning strategies (DQN / PPO / SAC / DDPG).

The runtime only depends on numpy/pandas for feature construction and model
metadata. The heavy training/inference stack (torch, stable-baselines3,
gymnasium) lives behind the optional ``[rl]`` extra and is imported lazily so
the default algorithm test-suite and CI stay dependency-free.
"""

from quant_platform.rl.errors import (
    RLDependenciesMissing,
    RLError,
    RLIncompatibleModel,
    RLInSampleRequest,
    RLModelNotFound,
    RLNotTrained,
)
from quant_platform.rl.policies import (
    RL_POLICIES,
    RL_STRATEGY_IDS,
    RLStrategy,
    augment_registry,
    is_rl_strategy_id,
    registry,
)

__all__ = [
    "RLDependenciesMissing",
    "RLError",
    "RLIncompatibleModel",
    "RLInSampleRequest",
    "RLModelNotFound",
    "RLNotTrained",
    "RL_POLICIES",
    "RL_STRATEGY_IDS",
    "RLStrategy",
    "augment_registry",
    "is_rl_strategy_id",
    "registry",
]
