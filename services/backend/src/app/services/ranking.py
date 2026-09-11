from __future__ import annotations

import logging
import math
import threading
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from datetime import date
from time import monotonic

from quant_platform.models import DataStatus, RankingItem
from quant_platform.ranking import StrategyRankingService as AlgorithmRankingService

from app.services.errors import InsufficientDataError, UpstreamUnavailableError
from app.services.research_dates import research_read
from app.services.strategies import StrategyCatalogService

logger = logging.getLogger(__name__)
_RANKING_BUDGET_SECONDS = 10.0
_CACHE_LIMIT = 128


class RankingService:
    """Revision-aware bounded cache, single-flight waits and cooperative I/O budget.

    The I/O budget bounds provider calls, not arbitrary CPU code. Results computed
    across a data revision or after the deadline are never cached or returned.
    """

    def __init__(
        self,
        algorithm: AlgorithmRankingService,
        provider: object,
        catalog: StrategyCatalogService,
    ) -> None:
        self._algorithm = algorithm
        self._provider = provider
        self._catalog = catalog
        self._cache: dict[tuple[date, str, str], list[RankingItem]] = {}
        self._condition = threading.Condition()
        self._inflight: set[tuple[date, str, str]] = set()

    def get_ranking(self, period: str) -> Mapping[str, object]:
        """返回契约 RankingResponse；period 已由路由层校验为枚举值之一。"""
        with research_read(self._provider) as context:
            as_of_date = date.fromisoformat(context["publicationDate"])
            items = self._compute(as_of_date, period)
        return {
            "dataContext": context,
            "asOfDate": as_of_date.isoformat(),
            "period": period,
            "items": [_serialize_item(item) for item in items],
        }

    def _latest_trade_date(self) -> date:
        """最新交易日来自数据源状态，None 表示本进程日更数据尚未就绪。"""
        status: DataStatus = self._provider.status()  # type: ignore[union-attr]
        if status.latest_trade_date is None:
            raise UpstreamUnavailableError(
                message="数据源尚未就绪：最新交易日未知",
                details={"reason": "latest_trade_date is None"},
            )
        return status.latest_trade_date

    def _revision(self) -> str:
        revision = getattr(self._provider, "cache_revision", None)
        return str(revision()) if callable(revision) else "unversioned"

    def _compute(self, as_of_date: date, period: str) -> list[RankingItem]:
        deadline = monotonic() + _RANKING_BUDGET_SECONDS
        revision = self._revision()
        key = (as_of_date, period, revision)
        with self._condition:
            while key in self._inflight:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise UpstreamUnavailableError(message="排行计算繁忙，请稍后重试")
                self._condition.wait(timeout=remaining)
            if key in self._cache:
                return self._cache[key]
            self._inflight.add(key)

        try:
            budget = getattr(self._provider, "computation_budget", None)
            context = budget(max(0, deadline - monotonic())) if callable(budget) else nullcontext()
            with context:
                items = self._algorithm.rank(as_of_date=as_of_date, period=period)
            if monotonic() > deadline:
                raise UpstreamUnavailableError(message="排行计算超时，请稍后重试")
            if self._revision() != revision:
                raise UpstreamUnavailableError(message="行情在计算期间更新，请重新获取排行")
            if not items:
                # 无策略产出真实结果（算法组吞掉异常等），显式报错而非 200 空排行
                raise InsufficientDataError(
                    message="没有策略产出真实结果，无法生成排行",
                    details={"period": period, "reason": "rank 返回空"},
                )
            items = self._validate_finite(items, period)
        except Exception:
            with self._condition:
                self._inflight.discard(key)
                self._condition.notify_all()
            raise

        with self._condition:
            if len(self._cache) >= _CACHE_LIMIT:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = items
            self._inflight.discard(key)
            self._condition.notify_all()
        self._log_missing(items)
        return items

    def _validate_finite(self, items: Sequence[RankingItem], period: str) -> list[RankingItem]:
        """任一指标非有限 → 整体 422，不让残缺条目进入排行。

        200 的 items 恒为全合法条目：要么完整返回，要么显式报错，
        消除"200 + 空排行"的费解状态。details 携带定位信息供排障。
        """
        for item in items:
            non_finite = [
                field
                for field, value in (
                    ("returnPct", item.return_pct),
                    ("maxDrawdownPct", item.max_drawdown_pct),
                    ("sharpe", item.sharpe),
                )
                if not math.isfinite(value)
            ]
            if non_finite:
                logger.warning(
                    "ranking: 策略 %s 指标 %s 非有限，返回 422", item.strategy_id, non_finite
                )
                raise InsufficientDataError(
                    message=f"策略 {item.strategy_id} 计算出现非有限指标，无法生成排行",
                    details={
                        "period": period,
                        "strategyId": item.strategy_id,
                        "field": non_finite[0],
                    },
                )
        return list(items)

    def _log_missing(self, items: Sequence[RankingItem]) -> None:
        """对照目录中 available 的策略，补上算法组静默吞异常的可观测性。"""
        available = {
            sid
            for sid, strategy in self._catalog.registry().items()
            if strategy.info().status == "available"
        }
        ranked = {item.strategy_id for item in items}
        for sid in sorted(available - ranked):
            logger.warning("ranking: available 策略 %s 未进入排行（可能执行失败）", sid)


def _serialize_item(item: RankingItem) -> dict[str, object]:
    """把算法组 RankingItem 翻译为契约字段（snake_case → camelCase）。"""
    return {
        "rank": item.rank,
        "strategyId": item.strategy_id,
        "strategyName": item.strategy_name,
        "category": item.category,
        "returnPct": item.return_pct,
        "maxDrawdownPct": item.max_drawdown_pct,
        "sharpe": item.sharpe,
    }
