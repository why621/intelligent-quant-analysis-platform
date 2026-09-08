from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping
from contextlib import closing
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.akshare_provider import (
    UpstreamUnavailableError as ProviderUpstreamError,
)
from quant_platform.models import BacktestRequest, BacktestResult, TradingCosts

from app.services.errors import (
    AssetNotFoundError,
    JobNotFoundError,
    StrategyNotAvailableError,
    ValidationError,
)
from app.services.parameters import validate_against_schema
from app.services.research_dates import ResearchDateGuard
from app.services.strategies import StrategyCatalogService

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_jobs (
    job_id              TEXT PRIMARY KEY,
    status              TEXT NOT NULL
                        CHECK (status IN ('queued','running','succeeded','failed')),
    request_json        TEXT NOT NULL,
    result_json         TEXT,
    error_code          TEXT,
    error_message       TEXT,
    error_details_json  TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    progress_pct        INTEGER NOT NULL DEFAULT 0
)
"""


def _now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


class BacktestJobStore:
    """回测任务表的存储后端：SQLite 单表，WAL + 短事务 + 每操作独立连接。

    状态迁移全部是单条原子 UPDATE（带 WHERE 状态条件），跨线程/跨进程安全，
    不需要锁：抢占 = "UPDATE ... WHERE status='queued'" 的 rowcount 仲裁。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with closing(_connect(self._db_path)) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def create(self, request: Mapping[str, object]) -> str:
        job_id = str(uuid.uuid4())
        with closing(_connect(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO backtest_jobs (job_id, status, request_json, created_at, progress_pct)"
                " VALUES (?, 'queued', ?, ?, 0)",
                (job_id, json.dumps(request), _now_iso()),
            )
            conn.commit()
        return job_id

    def claim(self) -> dict | None:
        """原子抢占一个 queued 任务并置为 running。

        子查询在写锁内选择任务，并发 worker 被写锁串行化后各自抢到不同任务；
        无任务时子查询返回 NULL，WHERE 不匹配任何行，返回 None。
        """
        with closing(_connect(self._db_path)) as conn:
            row = conn.execute(
                "UPDATE backtest_jobs SET status='running', updated_at=?, progress_pct=50"
                " WHERE job_id = (SELECT job_id FROM backtest_jobs"
                "                 WHERE status='queued' ORDER BY created_at LIMIT 1)"
                " RETURNING job_id, request_json",
                (_now_iso(),),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def mark_succeeded(self, job_id: str, result_json: str) -> None:
        with closing(_connect(self._db_path)) as conn:
            conn.execute(
                "UPDATE backtest_jobs SET status='succeeded', result_json=?,"
                " updated_at=?, progress_pct=100 WHERE job_id=?",
                (result_json, _now_iso(), job_id),
            )
            conn.commit()

    def mark_failed(self, job_id: str, error: Mapping[str, object]) -> None:
        with closing(_connect(self._db_path)) as conn:
            conn.execute(
                "UPDATE backtest_jobs SET status='failed', error_code=?, error_message=?,"
                " error_details_json=?, updated_at=? WHERE job_id=?",
                (
                    str(error["code"]),
                    str(error["message"]),
                    json.dumps(error.get("details")),
                    _now_iso(),
                    job_id,
                ),
            )
            conn.commit()

    def get(self, job_id: str) -> dict | None:
        with closing(_connect(self._db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM backtest_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            return dict(row) if row else None

    def recover_running(self) -> int:
        with closing(_connect(self._db_path)) as conn:
            cur = conn.execute(
                "UPDATE backtest_jobs SET status='queued', updated_at=? WHERE status='running'",
                (_now_iso(),),
            )
            conn.commit()
            return cur.rowcount


class BacktestService:
    """回测接口的实现：提交、查询、执行任务。

    服务层无状态：所有可变数据都在 SQLite 任务表；任务参数以提交时刻的
    request_json 快照为准，与其他请求完全隔离。
    """

    def __init__(
        self,
        store: BacktestJobStore,
        catalog: StrategyCatalogService,
        provider: object,
        engine: BacktestEngine,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._provider = provider
        self._engine = engine

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """业务校验后接受任务，返回 queued 的 BacktestJob（契约 BacktestJob 字段）。"""
        self._validate_business(payload)
        symbols = list(payload["symbols"])
        benchmark = payload.get("benchmark")
        if benchmark is not None:
            supported = {a.symbol for a in self._provider.list_assets(
                query=None, asset_type="etf", limit=None
            ) if a.asset_type == "etf" and a.active}
            if benchmark not in supported:
                raise ValidationError(
                    message="基准仅支持资产目录中的ETF；独立指数尚未接入",
                    details={"field": "benchmark", "benchmark": benchmark},
                )
            symbols.append(benchmark)
        ResearchDateGuard(self._provider).validate(
            symbols, date.fromisoformat(str(payload["startDate"])),
            date.fromisoformat(str(payload["endDate"])),
        )
        job_id = self._store.create(payload)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Mapping[str, object]:
        row = self._store.get(job_id)
        if row is None:
            raise JobNotFoundError(details={"jobId": job_id})
        return _serialize_job(row)

    def execute_job(self, job_id: str) -> None:
        """执行一个任务（被 worker 抢占后调用；测试也用它推进任务）。"""
        row = self._store.get(job_id)
        if row is None:
            return
        try:
            request = _build_request(json.loads(row["request_json"]))
            result = self._engine.run(request)
            self._store.mark_succeeded(job_id, json.dumps(_serialize_result(result)))
            logger.info("backtest job %s succeeded", job_id)
        except ProviderUpstreamError as exc:
            self._store.mark_failed(
                job_id,
                {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": "数据源暂时不可用，请稍后重试",
                    "details": {"jobId": job_id},
                },
            )
            logger.warning("backtest job %s failed upstream: %s", job_id, exc)
        except Exception:
            logger.exception("backtest job %s failed unexpectedly", job_id)
            self._store.mark_failed(
                job_id,
                {
                    "code": "INTERNAL_ERROR",
                    "message": "回测执行失败，请稍后重试",
                    "details": {"jobId": job_id},
                },
            )

    def _validate_business(self, payload: Mapping[str, object]) -> None:
        """提交时的业务校验：资产池、策略可用性、参数合法性（同步失败快报）。"""
        pool = {
            asset.symbol
            for asset in self._provider.list_assets(query=None, asset_type=None, limit=None)  # type: ignore[union-attr]
        }
        for symbol in payload["symbols"]:  # type: ignore[union-attr]
            if symbol not in pool:
                raise AssetNotFoundError(details={"symbol": symbol})

        strategy_id = str(payload["strategyId"])
        strategy = self._catalog.get_strategy(strategy_id)
        if strategy is None or strategy.info().status != "available":
            raise StrategyNotAvailableError(details={"strategyId": strategy_id})

        # 结构校验：以策略 info() 暴露的 parameterSchema 为唯一来源
        # （与 /strategies 接口给前端的约束一致），再走算法组语义校验。
        parameters = payload.get("parameters") or {}
        schema_errors = validate_against_schema(
            strategy.info().parameter_schema, parameters
        )
        if schema_errors:
            field, message = schema_errors[0]
            raise ValidationError(
                message=f"参数 {field} {message}",
                details={"strategyId": strategy_id, "field": field},
            )

        try:
            strategy.validate_parameters(parameters)
        except ValueError as exc:
            raise ValidationError(
                message=str(exc), details={"strategyId": strategy_id}
            ) from exc


class BacktestWorker:
    """后台线程：轮询抢占 queued 任务并执行。daemon 线程随进程退出。

    单 worker 串行执行；将来多 worker 部署时直接多启动几个实例，
    原子抢占保证同一任务不会被重复执行。
    """

    POLL_INTERVAL_SECONDS = 0.5

    def __init__(self, store: BacktestJobStore, service: BacktestService) -> None:
        self._store = store
        self._service = service
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="backtest-worker", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                job = self._store.claim()
            except Exception:
                logger.exception("backtest worker failed to claim a job")
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue
            if job is None:
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue
            try:
                self._service.execute_job(job["job_id"])
            except Exception:
                # execute_job handles algorithm failures itself. This guard keeps
                # the worker alive if persistence or another infrastructure step fails.
                logger.exception("backtest worker crashed while executing job %s", job["job_id"])


def _build_request(payload: Mapping[str, object]) -> BacktestRequest:
    """把路由层校验后的请求 dict（camelCase）翻译为算法组 BacktestRequest。"""
    trading_costs = payload.get("tradingCosts")
    return BacktestRequest(
        symbols=tuple(payload["symbols"]),  # type: ignore[arg-type]
        strategy_id=str(payload["strategyId"]),
        start_date=date.fromisoformat(str(payload["startDate"])),
        end_date=date.fromisoformat(str(payload["endDate"])),
        parameters=dict(payload.get("parameters") or {}),
        benchmark=payload.get("benchmark"),
        initial_capital_cny=float(payload.get("initialCapitalCny", 100000)),
        adjust=payload.get("adjust", "qfq"),  # type: ignore[arg-type]
        trading_costs=TradingCosts(
            commission_pct=float(trading_costs["commissionPct"]) if trading_costs else 0.03,
            stamp_duty_pct=float(trading_costs["stampDutyPct"]) if trading_costs else 0.05,
            slippage_pct=float(trading_costs["slippagePct"]) if trading_costs else 0.02,
        ),
    )


def _serialize_job(row: Mapping[str, object]) -> Mapping[str, object]:
    """把任务表一行翻译为契约 BacktestJob（snake_case → camelCase）。"""
    error = None
    if row["error_code"]:
        error = {
            "error": {
                "code": row["error_code"],
                "message": row["error_message"] or "",
                "details": (
                    json.loads(row["error_details_json"])
                    if row["error_details_json"]
                    else {}
                ),
            }
        }
    return {
        "request": json.loads(row["request_json"]),
        "jobId": row["job_id"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "progressPct": row["progress_pct"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": error,
    }


def _serialize_result(result: BacktestResult) -> Mapping[str, object]:
    """把算法组 BacktestResult 翻译为契约 BacktestResult（snake_case → camelCase）。"""
    metrics = result.metrics
    equity_curve = [
        {
            "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            "equity": float(row["equity"]),
            "benchmarkEquity": (
                None if pd.isna(row["benchmarkEquity"]) else float(row["benchmarkEquity"])
            ),
        }
        for _, row in result.equity_curve.iterrows()
    ]
    trades = [
        {
            "date": trade.trade_date.isoformat(),
            "symbol": trade.symbol,
            "side": trade.side,
            "price": float(trade.price),
            "quantity": float(trade.quantity),
            "amountCny": float(trade.amount_cny),
            "feeCny": float(trade.fee_cny),
        }
        for trade in result.trades
    ]
    return {
        "metrics": {
            "totalReturnPct": metrics.total_return_pct,
            "annualizedReturnPct": metrics.annualized_return_pct,
            "maxDrawdownPct": metrics.max_drawdown_pct,
            "sharpe": metrics.sharpe,
            "alphaPct": metrics.alpha_pct,
            "beta": metrics.beta,
        },
        "equityCurve": equity_curve,
        "trades": trades,
        "assumptions": dict(result.assumptions),
    }
