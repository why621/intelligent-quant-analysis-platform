from __future__ import annotations

import json
import logging
import math
import threading
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from copy import deepcopy
from datetime import date
from hashlib import sha256
from time import monotonic

from quant_platform.data.akshare_provider import UpstreamUnavailableError as ProviderUpstreamError
from quant_platform.data.calendar import sessions
from quant_platform.models import DataStatus, RankingItem
from quant_platform.ranking import RankingResult
from quant_platform.ranking import StrategyRankingService as AlgorithmRankingService
from quant_platform.rl.errors import RLError

from app.services.backtests import _build_request, _serialize_result
from app.services.errors import (
    InsufficientDataError,
    ServiceError,
    UpstreamUnavailableError,
    ValidationError,
)
from app.services.research_dates import research_read
from app.services.rl import RLServiceError
from app.services.strategies import StrategyCatalogService

logger = logging.getLogger(__name__)
_RANKING_BUDGET_SECONDS = 10.0
_CACHE_LIMIT = 128
_RESEARCH_BUDGET_SECONDS = 30.0
_RESEARCH_CONCURRENCY = 2


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
        *,
        backtests=None,
    ) -> None:
        self._algorithm = algorithm
        self._provider = provider
        self._catalog = catalog
        self._backtests = backtests
        self._research_cache: dict[str, dict] = {}
        self._research_inflight: set[str] = set()
        self._cache: dict[tuple[date, str, str, tuple], list[RankingItem]] = {}
        self._condition = threading.Condition()
        self._inflight: set[tuple[date, str, str, tuple]] = set()

    def get_ranking(self, period: str) -> Mapping[str, object]:
        """返回契约 RankingResponse；period 已由路由层校验为枚举值之一。"""
        with research_read(self._provider) as context:
            as_of_date = date.fromisoformat(context["publicationDate"])
            items = self._compute(as_of_date, period)
        return {
            "dataContext": context,
            "asOfDate": as_of_date.isoformat(),
            "evaluationSymbols": ["510300"],
            "period": period,
            "items": [_serialize_item(item) for item in items],
            "unavailableStrategies": list(getattr(items, "unavailable", ())),
            **getattr(items, "metadata", {}),
        }

    def _model_identity(self):
        """Include defaults, availability and reviewed model identities, not just IDs."""
        return deepcopy([
            {"id": sid, "status": strategy.info().status,
             "parameters": strategy.info().parameter_schema,
             "enabled": bool(getattr(strategy, "backtest_enabled", False)),
             "model": strategy.model_context() if hasattr(strategy, "model_context") else None}
            for sid, strategy in sorted(self._catalog.registry().items())
        ])

    def get_research_ranking(self, payload):
        """Execute the current research configuration without persisting backtest jobs.

        Every row goes through the same validator and engine as /backtests. No
        window clipping, fee substitution, benchmark or symbol fallback is used.
        A bounded cache and single-flight protect inference and provider calls.
        """
        if self._backtests is None:
            raise UpstreamUnavailableError("研究排行榜未装配")
        config = _normalize_request(payload)
        deadline = monotonic() + _RESEARCH_BUDGET_SECONDS
        identity = self._model_identity()
        revision = self._revision()
        key = None
        claimed = False
        try:
            with research_read(self._provider) as context:
                key = _digest({"request": config, "data": context,
                               "revision": revision, "strategies": identity})
                with self._condition:
                    while key in self._research_inflight:
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            raise UpstreamUnavailableError("研究排行计算繁忙，请稍后重试")
                        self._condition.wait(timeout=remaining)
                    if key in self._research_cache:
                        if self._model_identity() != identity:
                            raise UpstreamUnavailableError("模型在等待期间更新，请重新计算排行")
                        return deepcopy(self._research_cache[key])
                    if len(self._research_inflight) >= _RESEARCH_CONCURRENCY:
                        raise UpstreamUnavailableError("研究排行计算繁忙，请稍后重试")
                    self._research_inflight.add(key)
                    claimed = True
                budget = getattr(self._provider, "computation_budget", None)
                scope = (budget(max(0, deadline - monotonic()))
                         if callable(budget) else nullcontext())
                with scope:
                    result = self._compute_research(config, deadline)
                if monotonic() > deadline:
                    raise UpstreamUnavailableError("研究排行计算超时，请缩短区间后重试")
                if self._revision() != revision or self._model_identity() != identity:
                    raise UpstreamUnavailableError("行情或模型在计算期间更新，请重新计算排行")
                result.update(request=config, dataContext=context,
                              asOfDate=context["publicationDate"], configHash=key)
            # research_read's exit check must succeed BEFORE any cache insertion.
            transient = {"UPSTREAM_UNAVAILABLE", "RANKING_FAILED", "INTERNAL_ERROR"}
            if not any(item["code"] in transient for item in result["unavailableStrategies"]):
                with self._condition:
                    if len(self._research_cache) >= _CACHE_LIMIT:
                        self._research_cache.pop(next(iter(self._research_cache)))
                    self._research_cache[key] = deepcopy(result)
            return result
        except RLError as exc:
            raise RLServiceError(exc) from exc
        except ProviderUpstreamError as exc:
            raise UpstreamUnavailableError() from exc
        finally:
            if claimed:
                with self._condition:
                    self._research_inflight.discard(key)
                    self._condition.notify_all()

    def _compute_research(self, config, deadline):
        # Selected strategy must itself be a valid, executable research request.
        effective, _ = self._backtests.validate_request(config)
        if _normalize_request(effective) != config:
            raise ValidationError("当前策略费用与研究配置不一致，请显式配置模型所需费用")
        start, end = (date.fromisoformat(config[k]) for k in ("startDate", "endDate"))
        expected_dates = tuple(day.isoformat() for day in sessions(start, end))
        if len(expected_dates) < 2:
            raise InsufficientDataError("排行区间至少需要两个交易日")
        items, unavailable = [], []
        for sid, strategy in self._catalog.registry().items():
            if monotonic() > deadline:
                raise UpstreamUnavailableError("研究排行计算超时，请缩短区间后重试")
            info = strategy.info()
            candidate = {**config, "strategyId": sid, "parameters": (
                deepcopy(config["parameters"]) if sid == config["strategyId"] else {
                    key: deepcopy(value["default"])
                    for key, value in info.parameter_schema.get("properties", {}).items()
                    if "default" in value
                }
            )}
            try:
                effective, model_context = self._backtests.validate_request(candidate)
                if _normalize_request(effective) != candidate:
                    raise ValidationError("模型固定费用不适用于当前排行配置")
                result = self._backtests._engine.run(_build_request(candidate))
                serialized = _serialize_result(result)
                metrics = serialized["metrics"]
                if not all(value is None or math.isfinite(value) for value in metrics.values()):
                    raise InsufficientDataError("策略返回非有限指标，未参与排行")
                actual_dates = tuple(point["date"] for point in serialized["equityCurve"])
                if actual_dates != expected_dates:
                    raise InsufficientDataError("策略未覆盖全部评价交易日，未截短区间参与排行")
                items.append({
                    "rank": 0, "strategyId": sid, "strategyName": info.name,
                    "category": info.category, "status": info.status,
                    "returnPct": metrics["totalReturnPct"],
                    "maxDrawdownPct": metrics["maxDrawdownPct"], "sharpe": metrics["sharpe"],
                    "parameters": candidate["parameters"], "metrics": metrics,
                    **({"modelContext": model_context} if model_context else {}),
                    **{key: serialized[key] for key in ("costSummary", "benchmarkContext")
                       if key in serialized},
                })
            except (ServiceError, RLError, ProviderUpstreamError, ValueError) as exc:
                if isinstance(exc, RLError):
                    exc = RLServiceError(exc)
                if isinstance(exc, ProviderUpstreamError):
                    exc = UpstreamUnavailableError()
                if sid == config["strategyId"]:
                    if isinstance(exc, ServiceError):
                        raise exc
                    raise InsufficientDataError(str(exc)) from exc
                unavailable.append({"strategyId": sid, "strategyName": info.name,
                                    "code": getattr(exc, "code", "INSUFFICIENT_DATA"),
                                    "message": str(exc)})
            except Exception:
                logger.exception("research ranking failed for %s", sid)
                if sid == config["strategyId"]:
                    raise UpstreamUnavailableError("当前策略计算失败，请稍后重试") from None
                unavailable.append({"strategyId": sid, "strategyName": info.name,
                                    "code": "RANKING_FAILED",
                                    "message": "策略计算失败，未参与排行"})
        if not items:
            raise InsufficientDataError("没有策略产出真实结果，无法生成排行",
                                        details={"unavailableStrategies": unavailable})
        items.sort(key=lambda item: (-item["returnPct"], item["strategyId"]))
        for rank, item in enumerate(items, 1):
            item["rank"] = rank
        return {"evaluationSymbols": list(config["symbols"]),
                "evaluationStartDate": expected_dates[0], "evaluationEndDate": expected_dates[-1],
                "observationCount": len(expected_dates),
                "tradingCosts": deepcopy(config["tradingCosts"]),
                "items": items, "unavailableStrategies": unavailable}

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
        models = tuple(
            (sid, s.model_context()["bundleHash"])
            for sid, s in self._catalog.registry().items()
            if getattr(s, "ranking_enabled", False) is True
        )
        key = (as_of_date, period, revision, models)
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
                    details={
                        "period": period,
                        "reason": "rank 返回空",
                        "unavailableStrategies": list(getattr(items, "unavailable", ())),
                    },
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
        return RankingResult(items, unavailable=getattr(items, "unavailable", ()),
                             metadata=getattr(items, "metadata", {}))

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
        "status": item.status,
        "parameters": dict(item.parameters),
        **({"modelContext": item.model_context} if item.model_context else {}),
    }


def _normalize_request(payload):
    # Mirrors _build_request defaults; all effective inputs are part of identity.
    value = {
        "symbols": list(payload["symbols"]), "strategyId": payload["strategyId"],
        "startDate": payload["startDate"], "endDate": payload["endDate"],
        "parameters": deepcopy(payload.get("parameters", {})),
        "initialCapitalCny": payload.get("initialCapitalCny", 100000),
        "adjust": payload.get("adjust", "qfq"), "cashPct": payload.get("cashPct", 0),
        "portfolioMode": payload.get("portfolioMode", "legacy_independent"),
        "benchmarkMode": payload.get("benchmarkMode") or (
            "custom" if payload.get("benchmark") else "none"),
        "tradingCosts": {"commissionPct": 0.03, "stampDutyPct": 0.05,
                         "slippagePct": 0.02, "stampDutyMode": "fixed",
                         **payload.get("tradingCosts", {})},
    }
    if payload.get("benchmark") is not None:
        value["benchmark"] = payload["benchmark"]
    return value


def _digest(value):
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("研究参数必须是有限、可序列化的JSON值") from exc
    return sha256(serialized.encode()).hexdigest()