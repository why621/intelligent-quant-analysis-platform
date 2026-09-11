from __future__ import annotations

from collections.abc import Mapping, Sequence

from quant_platform.allocation import AllocationService as AlgorithmAllocationService
from quant_platform.allocation import PublicationUnavailableError, StalePublicationError
from quant_platform.data.akshare_provider import (
    UpstreamUnavailableError as ProviderUpstreamError,
)
from quant_platform.models import AllocationSuggestion

from app.services.errors import ServiceError, StrategyNotAvailableError, UpstreamUnavailableError
from app.services.research_dates import DataNotReadyError, research_read
from app.services.strategies import StrategyCatalogService


class DataStaleError(ServiceError):
    code = "DATA_STALE"
    status = 503
    message = "已发布行情尚未覆盖所需交易日，暂不能生成当前模拟配置"


class AllocationService:
    """下一交易日模拟配置建议接口的实现。

    服务层无状态：只依赖共享的策略目录（只读）与算法组 AllocationService。
    每次请求的信号计算是纯函数式的（history → generate_signals → 等权），
    请求间无共享可变状态——并发安全是构造性的，不需要锁也不需要缓存。

    算法层核对已发布截止与上海日期之前最近交易日，校验数据及信号；
    数据不足或过期按上游不可用返回，不生成伪中性建议。
    """

    def __init__(
        self,
        algorithm: AlgorithmAllocationService,
        catalog: StrategyCatalogService,
    ) -> None:
        self._algorithm = algorithm
        self._catalog = catalog

    def suggest(
        self,
        *,
        symbols: Sequence[str],
        strategy_id: str,
        cash_pct: float,
    ) -> Mapping[str, object]:
        """返回契约 AllocationResponse；字段已由路由层校验。"""
        strategy = self._catalog.get_strategy(strategy_id)
        if strategy is None or strategy.info().status != "available":
            raise StrategyNotAvailableError(details={"strategyId": strategy_id})

        try:
            with research_read(self._algorithm._provider) as context:
                result = self._algorithm.suggest(
                    symbols=symbols,
                    strategy_id=strategy_id,
                    cash_pct=cash_pct,
                )
        except PublicationUnavailableError as exc:
            raise DataNotReadyError() from exc
        except StalePublicationError as exc:
            raise DataStaleError(
                details={
                    "availableEndDate": exc.available.isoformat(),
                    "requiredEndDate": exc.required.isoformat(),
                }
            ) from exc
        except ProviderUpstreamError as exc:
            raise UpstreamUnavailableError(details={"capability": "allocation-suggestion"}) from exc
        except ValueError as exc:
            # 算法组对未知策略抛 ValueError；目录外策略已被前置校验拦截，
            # 此处兜底统一转为契约错误码
            raise StrategyNotAvailableError(
                message=str(exc), details={"strategyId": strategy_id}
            ) from exc
        return {**_serialize_suggestion(result), "dataContext": context}


def _serialize_suggestion(result: AllocationSuggestion) -> Mapping[str, object]:
    """把算法组 AllocationSuggestion 翻译为契约字段（snake_case → camelCase）。"""
    return {
        "basisDate": result.basis_date.isoformat(),
        "targetDate": result.target_date.isoformat(),
        "strategyId": result.strategy_id,
        "positions": [
            {
                "symbol": position.symbol,
                "weightPct": position.weight_pct,
                "action": position.action,
                "reason": position.reason,
            }
            for position in result.positions
        ],
        "cashPct": result.cash_pct,
        "advisoryOnly": result.advisory_only,
        "disclaimer": result.disclaimer,
    }
