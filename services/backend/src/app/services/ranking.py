from __future__ import annotations

import logging
import math
import threading
from collections.abc import Mapping, Sequence
from datetime import date

from quant_platform.models import DataStatus, RankingItem
from quant_platform.ranking import StrategyRankingService as AlgorithmRankingService

from app.services.errors import InsufficientDataError, UpstreamUnavailableError
from app.services.strategies import StrategyCatalogService

logger = logging.getLogger(__name__)


class RankingService:
    """策略排行接口的实现：数据驱动 asOfDate + 查表缓存 + single-flight 并发合并。

    服务层无状态；唯一共享的是线程安全的缓存。缓存是 write-once 语义：
    一个 key（asOfDate, period）一生只写一次（single-flight 保证），写后
    永不修改、从不删除——因此读路径可以无锁（CPython 的 dict.get 是
    原子操作，与写 key 不交错），只有 miss 才进锁区。
    排行是日更快照：key 含 asOfDate，数据日更后 key 变化 → 查表 miss →
    自然重算。"失效"由 miss 隐式表达，无需任何过期检查。
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
        self._cache: dict[tuple[date, str], list[RankingItem]] = {}
        self._condition = threading.Condition()
        # 正在计算中的 key 集合：多 key 并发（不同 period / asOfDate 变化瞬间）
        # 各自独立合并，互不覆盖——单值标记会在 key2 插入时把 key1 的标记顶掉
        self._inflight: set[tuple[date, str]] = set()

    def get_ranking(self, period: str) -> Mapping[str, object]:
        """返回契约 RankingResponse；period 已由路由层校验为枚举值之一。"""
        as_of_date = self._latest_trade_date()
        items = self._compute(as_of_date, period)
        return {
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

    def _compute(self, as_of_date: date, period: str) -> list[RankingItem]:
        """缓存未命中时计算一次；并发请求被 single-flight 合并为一次计算。

        双层检查：第一重无锁 get（write-once 缓存，命中即返回）；miss 才
        进锁区做第二重检查（等别人算完或自己成为计算者）。计算不持锁
        （耗时操作），结果完整构造后原子写入并唤醒所有等待者；异常同样
        唤醒等待者自行重试（错误不缓存）。
        """
        key = (as_of_date, period)

        # 第一重检查：无锁读。write-once 不变量——key 写入后不再修改、
        # 从不删除；dict.get 在 GIL 下是原子操作，与写 key 不交错，读线程
        # 要么 miss 要么看到完整值，不存在读到半写状态的中间态。
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        with self._condition:
            while key in self._inflight:
                self._condition.wait()
            if key in self._cache:  # 第二重检查：等待期间别人可能已写好
                return self._cache[key]
            self._inflight.add(key)

        try:
            items = self._algorithm.rank(as_of_date=as_of_date, period=period)  # type: ignore[arg-type]
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
