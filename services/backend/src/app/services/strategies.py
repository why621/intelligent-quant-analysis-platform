from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant_platform.interfaces import Strategy
from quant_platform.models import StrategyInfo
from quant_platform.strategies.ma_cross import MACrossStrategy
from quant_platform.strategies.momentum_reversal import MomentumReversalStrategy


class StrategyCatalogService:
    """策略目录接口的实现：聚合算法组各策略的元数据并翻译为契约 JSON。

    算法组没有统一的目录入口，每个策略类各自暴露 info()，
    因此后端维护策略注册表；新增策略时在 _strategies 里加一条即可。
    """

    def __init__(self, strategies: Sequence[Strategy] | None = None) -> None:
        self._strategies = (
            list(strategies)
            if strategies is not None
            else [MACrossStrategy(), MomentumReversalStrategy()]
        )
        self._by_id = {s.info().strategy_id: s for s in self._strategies}

    def list_strategies(self) -> Mapping[str, object]:
        """返回策略目录，字段与 contracts/schemas/strategy.yaml#/Strategy 一致。"""
        return {"items": [_serialize_strategy(s.info()) for s in self._strategies]}

    def get_strategy(self, strategy_id: str) -> Strategy | None:
        """按 id 返回策略实例（供参数校验和回测引擎使用）；不存在时返回 None。"""
        return self._by_id.get(strategy_id)

    def registry(self) -> Mapping[str, Strategy]:
        """返回 id → 策略实例 的映射，供回测引擎注入。"""
        return dict(self._by_id)


def _serialize_strategy(info: StrategyInfo) -> dict[str, object]:
    """把算法组的 StrategyInfo 翻译成契约 Strategy（snake_case → camelCase）。"""
    return {
        "id": info.strategy_id,
        "name": info.name,
        "category": info.category,
        "status": info.status,
        "description": info.description,
        "parameterSchema": info.parameter_schema,
    }
