"""SB3-backed single-agent strategies implementing the repo ``Strategy`` protocol.

A shared registry instance carries only metadata — it can describe itself and
validate parameters but refuses to emit signals (``RLNotTrained``). The engine
resolves a *per-request* instance via ``create_for_request`` which loads the
trained bundle from the model store; that instance never re-fits and rejects
any backtest that overlaps its own training window. torch / stable-baselines3 /
gymnasium are imported only inside the load-and-predict path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from quant_platform.models import SignalSemantics, StrategyInfo
from quant_platform.rl import features
from quant_platform.rl.errors import RLIncompatibleModel, RLInSampleRequest, RLNotTrained

DEFAULT_MODELS_ROOT = Path(__file__).resolve().parents[5] / "models"


@dataclass(frozen=True)
class RLAlgorithmSpec:
    algo_id: str
    name: str
    sb3_class: str
    discrete: bool
    signal_semantics: SignalSemantics
    description: str
    hyperparameters: Mapping[str, object] = field(default_factory=dict)


DQN = RLAlgorithmSpec(
    algo_id="dqn",
    name="DQN 强化学习",
    sb3_class="DQN",
    discrete=True,
    signal_semantics="discrete_hold",
    description=(
        "深度 Q 网络学习满仓/空仓两种动作。收盘决策、次日开盘成交；"
        "回测需指定已训练权重 modelRef，且只能在训练窗口之外使用。"
    ),
    hyperparameters={"learning_rate": 1e-3, "buffer_size": 100_000, "target_update_interval": 500},
)
PPO = RLAlgorithmSpec(
    algo_id="ppo",
    name="PPO 强化学习",
    sb3_class="PPO",
    discrete=False,
    signal_semantics="continuous_target_weight",
    description=(
        "近端策略优化输出连续目标权重（仅做多）。收盘决策、次日开盘成交；"
        "回测需指定已训练权重 modelRef，且只能在训练窗口之外使用。"
    ),
    hyperparameters={"learning_rate": 3e-4, "n_steps": 2048, "batch_size": 64},
)
SAC = RLAlgorithmSpec(
    algo_id="sac",
    name="SAC 强化学习",
    sb3_class="SAC",
    discrete=False,
    signal_semantics="continuous_target_weight",
    description=(
        "Soft Actor-Critic 输出最大熵连续目标权重（仅做多）。收盘决策、次日开盘成交；"
        "回测需指定已训练权重 modelRef，且只能在训练窗口之外使用。"
    ),
    hyperparameters={"learning_rate": 3e-4, "buffer_size": 200_000, "batch_size": 256},
)
DDPG = RLAlgorithmSpec(
    algo_id="ddpg",
    name="DDPG 强化学习",
    sb3_class="DDPG",
    discrete=False,
    signal_semantics="continuous_target_weight",
    description=(
        "深度确定性策略梯度输出确定性连续目标权重（仅做多）。收盘决策、次日开盘成交；"
        "回测需指定已训练权重 modelRef，且只能在训练窗口之外使用。"
    ),
    hyperparameters={"learning_rate": 3e-4, "buffer_size": 200_000, "batch_size": 256},
)

RL_POLICIES: dict[str, RLAlgorithmSpec] = {s.algo_id: s for s in (DQN, PPO, SAC, DDPG)}
RL_STRATEGY_IDS: frozenset[str] = frozenset(RL_POLICIES)


def is_rl_strategy_id(strategy_id: str) -> bool:
    return strategy_id in RL_STRATEGY_IDS


def default_store():
    from quant_platform.rl.store import ModelStore

    return ModelStore(DEFAULT_MODELS_ROOT)


def _parameter_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["modelRef"],
        "properties": {
            "modelRef": {
                "type": "string",
                "description": "已训练权重 run-id（对应 /models/<run-id>），不可回退到未训练实例。",
            },
        },
    }


class RLStrategy:
    """Metadata-only shared instance; becomes an inference instance via the store."""

    def __init__(
        self,
        spec: RLAlgorithmSpec,
        *,
        store=None,
        bundle=None,
        model=None,
        rebalance_band_pct: float = 0.005,
        min_trade_cny: float = 100.0,
    ) -> None:
        self._spec = spec
        self._store = store
        self._bundle = bundle
        self._model = model
        self.rebalance_band_pct = rebalance_band_pct
        self.min_trade_cny = min_trade_cny

    @property
    def id(self) -> str:
        return self._spec.algo_id

    @property
    def requires_trained_model(self) -> bool:
        return True

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            strategy_id=self._spec.algo_id,
            name=self._spec.name,
            category="ai",
            status="experimental",
            description=self._spec.description,
            parameter_schema=_parameter_schema(),
            signal_semantics=self._spec.signal_semantics,
            requires_trained_model=True,
        )

    def validate_parameters(self, parameters: Mapping[str, object]) -> None:
        unknown = set(parameters) - {"modelRef"}
        if unknown:
            raise ValueError(f"未知参数: {sorted(unknown)}")
        ref = parameters.get("modelRef")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("modelRef 必须是非空字符串（已训练权重的 run-id）")

    def create_for_request(self, parameters: Mapping[str, object]) -> RLStrategy:
        """Return a fresh inference instance bound to the requested trained model."""
        self.validate_parameters(parameters)
        from quant_platform.rl.store import ModelBundle

        bundle: ModelBundle = (self._store or default_store()).load(parameters["modelRef"])
        self._verify_bundle(bundle)
        instance = RLStrategy(
            self._spec,
            store=self._store,
            bundle=bundle,
            rebalance_band_pct=self.rebalance_band_pct,
            min_trade_cny=self.min_trade_cny,
        )
        instance._load_model()
        return instance

    def _verify_bundle(self, bundle) -> None:
        """Refuse a bundle that is not this strategy trained on this feature recipe.

        ``modelRef`` alone cannot prove the artifact matches — a PPO request
        pointed at a DQN run, or a run built under a different feature recipe,
        would otherwise load and emit silently-wrong weights.
        """
        manifest = bundle.manifest
        recorded_algo = manifest.get("algo")
        if recorded_algo != self._spec.algo_id:
            raise RLIncompatibleModel(
                f"modelRef 训练算法为 {recorded_algo!r}，与请求策略 {self._spec.algo_id!r} 不符"
            )
        recorded_sig = manifest.get("featureSignature")
        current_sig = features.feature_signature()
        if recorded_sig != current_sig:
            raise RLIncompatibleModel(
                f"模型特征配方签名 {recorded_sig!r} 与当前 {current_sig!r} 不符，拒绝混版推理"
            )

    # -- heavy, model-backed paths -----------------------------------------

    def _load_model(self) -> None:
        if self._bundle is None:
            raise RLNotTrained("no model bundle loaded")
        try:
            import io

            from stable_baselines3 import DDPG, DQN, PPO, SAC
        except ImportError as exc:  # pragma: no cover - exercised only without [rl]
            from quant_platform.rl.errors import RLDependenciesMissing

            raise RLDependenciesMissing(
                "强化学习依赖缺失，请安装 extras: pip install -e \"services/algorithms[rl]\""
            ) from exc
        classes = {"DQN": DQN, "PPO": PPO, "SAC": SAC, "DDPG": DDPG}
        model_cls = classes[self._spec.sb3_class]
        self._model = model_cls.load(io.BytesIO(self._bundle.model_bytes))

    def generate_signals(
        self,
        prices: pd.DataFrame,
        parameters: Mapping[str, object],
    ) -> pd.Series:
        if self._bundle is None or self._model is None:
            raise RLNotTrained(
                f"策略 {self._spec.algo_id} 需先训练并用 modelRef 指定权重，未训练实例不出信号。"
            )
        self._reject_in_sample(prices)
        return self._predict_weights(prices)

    def _reject_in_sample(self, prices: pd.DataFrame) -> None:
        train_end = str(self._bundle.manifest.get("trainEndDate", ""))
        if not train_end or prices.empty or "date" not in prices.columns:
            return
        first = pd.Timestamp(prices["date"].iloc[0]).date().isoformat()
        if first <= train_end:
            raise RLInSampleRequest(
                f"回测起始 {first} 落在训练窗口内（trainEndDate={train_end}），拒绝样本内评估。"
            )

    def _predict_weights(self, prices: pd.DataFrame) -> pd.Series:
        from quant_platform.rl.env import TradingEnv

        env = TradingEnv(prices, discrete=self._spec.discrete)
        frame = prices.reset_index(drop=True)
        weights = np.full(len(frame), np.nan, dtype=float)

        obs, _ = env.reset()
        done = False
        while not done:
            action, _ = self._model.predict(obs, deterministic=True)
            bar = env._step_index
            if 0 <= bar < len(weights):
                weights[bar] = env._target_weight(action)
            obs, _, done, _, _ = env.step(action)

        signal = pd.Series(weights, index=frame.index, dtype=float)
        if self._spec.signal_semantics == "discrete_hold":
            # DQN is long/flat: all-in -> +1, flat -> -1 so the engine liquidates.
            raw = signal.to_numpy()
            out = np.where(np.isnan(raw), 0.0, np.where(raw > 0.5, 1.0, -1.0))
            return pd.Series(out, index=frame.index, dtype=float)
        return signal


def registry(*, store=None) -> dict[str, RLStrategy]:
    """Untrained shared instances keyed by id, for callers that opt RL in."""
    return {sid: RLStrategy(spec, store=store) for sid, spec in RL_POLICIES.items()}


def augment_registry(base, *, include_rl: bool = True, store=None) -> dict:
    """Return a copy of ``base`` with the four RL strategies added when opted in.

    A single switch for the backend so RL can be enumerated off by default and
    turned on per environment without touching the shared strategy list.
    """
    merged = dict(base)
    if include_rl:
        merged.update(registry(store=store))
    return merged
