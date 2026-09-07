from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

from quant_platform.data import upstream
from quant_platform.data.calendar import CalendarUnavailableError, latest_session, sessions
from quant_platform.data.storage import DataStatusStore, MarketOverviewStore, OHLCVStore
from quant_platform.models import AdjustMode, Asset, AssetType, DataStatus

# 30–50 个 A 股/ETF 资产池，代码全部六位字符串
_DEFAULT_UNIVERSE: list[dict[str, str]] = [
    # 宽基 ETF
    {"symbol": "510300", "name": "沪深300ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "510500", "name": "中证500ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "510050", "name": "上证50ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "159915", "name": "创业板ETF", "asset_type": "etf", "exchange": "SZSE"},
    {"symbol": "159919", "name": "沪深300ETF", "asset_type": "etf", "exchange": "SZSE"},
    {"symbol": "159922", "name": "中证500ETF", "asset_type": "etf", "exchange": "SZSE"},
    {"symbol": "510880", "name": "红利ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512880", "name": "证券ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512100", "name": "中证1000ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "159845", "name": "中证1000ETF", "asset_type": "etf", "exchange": "SZSE"},
    {"symbol": "513100", "name": "纳指ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "513500", "name": "标普500ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "510900", "name": "H股ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "518880", "name": "黄金ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "511260", "name": "十年国债ETF", "asset_type": "etf", "exchange": "SSE"},
    # 行业 ETF
    {"symbol": "512690", "name": "酒ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512660", "name": "军工ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "516510", "name": "芯片ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "515790", "name": "光伏ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512980", "name": "传媒ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "159996", "name": "家电ETF", "asset_type": "etf", "exchange": "SZSE"},
    {"symbol": "515050", "name": "AIETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512170", "name": "医疗ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512010", "name": "医药ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "512580", "name": "碳中和ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "516160", "name": "新能源ETF", "asset_type": "etf", "exchange": "SSE"},
    {"symbol": "159766", "name": "旅游ETF", "asset_type": "etf", "exchange": "SZSE"},
    # A 股龙头
    {"symbol": "600519", "name": "贵州茅台", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "000858", "name": "五粮液", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "601318", "name": "中国平安", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "000333", "name": "美的集团", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "600036", "name": "招商银行", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "002415", "name": "海康威视", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "600276", "name": "恒瑞医药", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "300750", "name": "宁德时代", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "000001", "name": "平安银行", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "601899", "name": "紫金矿业", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "600900", "name": "长江电力", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "002594", "name": "比亚迪", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "300059", "name": "东方财富", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "601888", "name": "中国中免", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "000725", "name": "京东方A", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "600030", "name": "中信证券", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "002475", "name": "立讯精密", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "600809", "name": "山西汾酒", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "300124", "name": "汇川技术", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "600585", "name": "海螺水泥", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "000568", "name": "泸州老窖", "asset_type": "stock", "exchange": "SZSE"},
    {"symbol": "601012", "name": "隆基绿能", "asset_type": "stock", "exchange": "SSE"},
    {"symbol": "002714", "name": "牧原股份", "asset_type": "stock", "exchange": "SZSE"},
]

INDEX_SYMBOLS = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
    ("000688", "科创50"),
    ("000300", "沪深300"),
    ("000905", "中证500"),
]

_LOOKBACK_DAYS = 400
_OVERVIEW_TIMEOUT_SECONDS = 180
_HISTORY_BATCH_TIMEOUT_SECONDS = 900
_OVERVIEW_ATTEMPTS = 1  # HTTP pages retry individually; do not restart a full collection.
logger = logging.getLogger(__name__)
_REQUEST_DEADLINE = ContextVar("history_request_deadline", default=None)


def _default_data_dir() -> Path:
    """Resolve writable storage without assuming the package lives in a source tree."""
    configured = os.getenv("QUANT_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "data" / "processed").resolve()


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _tencent_symbol(symbol: str) -> str:
    """六位代码 → 腾讯带市场前缀的代码。"""
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


class UpstreamUnavailableError(RuntimeError):
    """The live market-data provider failed and no result can be trusted."""


class AkShareMarketDataProvider:
    """AkShare 数据适配器——算法模块中唯一允许了解 AkShare API 细节的类。

    history() 优先读取 SQLite 行情缓存，缓存覆盖不了再调用腾讯接口；
    update_daily() 收盘后增量拉取并写入 SQLite，市场概况保存为原子替换的 JSON 快照。
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        request_interval_seconds: float = 0.2,
    ) -> None:
        self._assets: dict[str, Asset] = {
            a["symbol"]: Asset(
                symbol=a["symbol"],
                name=a["name"],
                asset_type=a["asset_type"],  # type: ignore[arg-type]
                exchange=a["exchange"],  # type: ignore[arg-type]
            )
            for a in _DEFAULT_UNIVERSE
        }
        resolved_data_dir = Path(data_dir).resolve() if data_dir else _default_data_dir()
        self._storage = OHLCVStore(resolved_data_dir)
        self._overview_storage = MarketOverviewStore(resolved_data_dir)
        self._status_storage = DataStatusStore(resolved_data_dir)
        self._request_interval_seconds = max(0.0, request_interval_seconds)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def list_assets(
        self,
        query: str | None = None,
        asset_type: AssetType | None = None,
        limit: int = 50,
    ) -> list[Asset]:
        result = list(self._assets.values())
        if query is not None:
            q = query.strip().lower()
            result = [a for a in result if q in a.symbol or q in a.name.lower()]
        if asset_type is not None:
            result = [a for a in result if a.asset_type == asset_type]
        return result[:limit]

    def history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        """先读缓存，缓存覆盖请求范围则直接返回；否则调腾讯接口并更新缓存。"""
        self._remaining_budget()
        try:
            expected = sessions(start_date, end_date)
        except CalendarUnavailableError as exc:
            raise UpstreamUnavailableError(str(exc)) from exc
        if not expected:
            return _empty_ohlcv()
        start_date, end_date = expected[0], expected[-1]
        cached = self._storage.load(symbol, adjust)
        if not cached.empty:
            lo = pd.Timestamp(start_date)
            hi = pd.Timestamp(end_date)
            if set(expected).issubset(set(cached["date"].dt.date)):
                return cached[(cached["date"] >= lo) & (cached["date"] <= hi)]

        fetch_start, fetch_end = start_date, end_date
        if adjust != "none" and not cached.empty:
            # Adjusted prices may revise the ENTIRE cached range after dividends.
            fetch_start = min(start_date, cached["date"].min().date())
            fetch_end = max(end_date, cached["date"].max().date())
        raw = self._fetch_tencent(symbol, fetch_start, fetch_end, adjust)
        if raw.empty:
            if not cached.empty:
                raise UpstreamUnavailableError("empty refresh cannot extend partial history cache")
            raise UpstreamUnavailableError("no history returned for requested trading sessions")
        if not set(expected).issubset(set(raw["date"].dt.date)):
            raise UpstreamUnavailableError("history has missing sessions; coverage is incomplete")
        self._validate_adjusted_refresh(cached, raw, adjust)

        # 合并缓存与 API 数据，去重后写回缓存
        if not cached.empty:
            merged = (
                pd.concat([cached, raw], ignore_index=True)
                .drop_duplicates(subset="date", keep="last")
                .sort_values("date")
            )
        else:
            merged = raw
        self._storage.save(symbol, merged, adjust)

        lo = pd.Timestamp(start_date)
        hi = pd.Timestamp(end_date)
        return merged[(merged["date"] >= lo) & (merged["date"] <= hi)]

    def status(self) -> DataStatus:
        """返回跨进程的日更状态。包含 fallback 的 asset counts。"""
        return self._status_storage.load(len(self._assets))

    def cache_revision(self) -> str:
        return self._storage.revision()

    @contextmanager
    def computation_budget(self, seconds: float):
        token = _REQUEST_DEADLINE.set(monotonic() + seconds)
        try:
            yield
        finally:
            _REQUEST_DEADLINE.reset(token)

    @staticmethod
    def _remaining_budget() -> float:
        deadline = _REQUEST_DEADLINE.get()
        remaining = 40.0 if deadline is None else min(40.0, deadline - monotonic())
        if remaining <= 0:
            raise UpstreamUnavailableError("history computation deadline exceeded")
        return remaining

    @staticmethod
    def _validate_adjusted_refresh(cached, fresh, adjust):
        if adjust != "none" and not cached.empty:
            if not set(cached["date"]).issubset(set(fresh["date"])):
                raise UpstreamUnavailableError(
                    "adjusted refresh does not cover old bars; refusing mixed adjustment bases"
                )

    def update_daily(self) -> DataStatus:
        """Incrementally refresh all assets once after market close."""
        today = _today()
        previous_status = self._status_storage.load(len(self._assets))
        self._status_storage.save(
            status="updating",
            latest_trade_date=previous_status.latest_trade_date,
            message="日更任务进行中",
            components={
                "history": {"status": "updating", "message": "行情日更进行中"},
                "overview": {"status": "updating", "message": "等待市场概览刷新"},
            },
        )
        available = 0
        refreshed = 0
        upstream_errors = 0
        failed_symbols: list[str] = []
        latest_date: date | None = None
        asset_dates: dict[str, date] = {}
        history_deadline = monotonic() + _HISTORY_BATCH_TIMEOUT_SECONDS

        for symbol in self._assets:
            try:
                cached = self._storage.load(symbol)
                if not cached.empty:
                    available += 1
                    cached_date = cached["date"].max().date()
                    if latest_date is None or cached_date > latest_date:
                        latest_date = cached_date
                    asset_dates[symbol] = cached_date
                    start = cached["date"].min().date()
                else:
                    start = today - timedelta(days=_LOOKBACK_DAYS)

                if start > today:
                    continue

                try:
                    if monotonic() >= history_deadline:
                        raise UpstreamUnavailableError("history batch deadline exceeded")
                    frame = self._fetch_tencent(symbol, start, today, "qfq")
                finally:
                    if self._request_interval_seconds:
                        sleep(self._request_interval_seconds)

                if frame.empty:
                    raise UpstreamUnavailableError("daily refresh returned no history rows")
                self._validate_adjusted_refresh(cached, frame, "qfq")

                merged = (
                    pd.concat([cached, frame], ignore_index=True)
                    .drop_duplicates(subset="date", keep="last")
                    .sort_values("date")
                )
                self._storage.save(symbol, merged)
                if cached.empty:
                    available += 1
                refreshed += 1
                merged_date = merged["date"].max().date()
                asset_dates[symbol] = merged_date
                if latest_date is None or merged_date > latest_date:
                    latest_date = merged_date
            except Exception:
                upstream_errors += 1
                failed_symbols.append(symbol)
                logger.exception("history refresh failed: symbol=%s", symbol)

        # Report the oldest available asset's end date, not the freshest asset's date.
        latest_date = min(asset_dates.values()) if asset_dates else None
        try:
            expected_end = latest_session(today)
        except CalendarUnavailableError:
            expected_end = today  # never label an unverified calendar ready
            upstream_errors += 1
        if any(day != expected_end for day in asset_dates.values()):
            for symbol, day in asset_dates.items():
                if day != expected_end and symbol not in failed_symbols:
                    failed_symbols.append(symbol)
                    upstream_errors += 1
        history_state = (
            "failed" if available == 0
            else "stale" if available < len(self._assets) or upstream_errors
            else "ready"
        )
        overview_state = "ready"
        overview_message = "市场概览刷新成功"
        try:
            self.refresh_market_overview()
        except (OSError, UpstreamUnavailableError, ValueError) as exc:
            upstream_errors += 1
            logger.exception("market overview refresh failed; retaining previous snapshot")
            overview_state = "stale" if self._overview_storage.load() else "failed"
            overview_message = (
                "刷新失败，保留上次成功快照" if overview_state == "stale"
                else "市场概览暂不可用，尚无成功快照"
            )
            overview_message += f"（{type(exc).__name__}）"

        total = len(self._assets)
        if available == 0:
            state = "failed"
        elif available < total or upstream_errors:
            state = "stale"
        else:
            state = "ready"

        self._status_storage.save(
            status=state,
            latest_trade_date=latest_date,
            message=(
                f"refreshed={refreshed}, available={available}/{total}, "
                f"upstreamErrors={upstream_errors}"
            ),
            components={
                "history": {
                    "status": history_state,
                    "message": f"刷新 {refreshed} 个，可用 {available}/{total} 个",
                    "failedSymbols": failed_symbols,
                },
                "overview": {
                    "status": overview_state,
                    "message": overview_message,
                },
            },
        )
        return self._status_storage.load(total)

    def market_overview(self, trade_date: date | None = None) -> dict[str, object]:
        """Read only: upstream refreshes belong to the scheduled CLI, never HTTP workers."""
        cached = self._overview_storage.load()
        if trade_date is not None:
            requested = trade_date.isoformat()
            if cached is None or cached.get("tradeDate") != requested:
                raise ValueError("the requested trade date is not available in the local cache")
        if cached is not None:
            return dict(cached)
        raise UpstreamUnavailableError("market overview unavailable; run quant-data-update")

    def refresh_market_overview(self) -> dict[str, object]:
        """Refresh and persist the market snapshot; intended for the daily CLI."""
        overview = self._fetch_overview_bounded(_today())
        self._overview_storage.save(overview)
        return overview

    def _fetch_overview_bounded(self, trade_date: date) -> dict[str, object]:
        try:
            return self._fetch_market_overview(trade_date)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            raise UpstreamUnavailableError("market overview failed validation or deadline") from exc

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _fetch_tencent(
        self, symbol: str, start_date: date, end_date: date, adjust: AdjustMode,
    ) -> pd.DataFrame:
        try:
            records = upstream.run("history", {
                "symbol": symbol, "start": start_date.isoformat(),
                "end": end_date.isoformat(), "adjust": adjust,
            }, timeout=self._remaining_budget())
            if not isinstance(records, list):
                raise ValueError("invalid history worker output")
            if not records:
                return _empty_ohlcv()
            frame = pd.DataFrame(records)
            frame["date"] = pd.to_datetime(frame["date"], errors="raise")
            for column in ["open", "high", "low", "close", "volume", "amount"]:
                frame[column] = pd.to_numeric(frame[column], errors="raise")
            return frame
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            raise UpstreamUnavailableError(f"Tencent history failed for {symbol}") from exc

    def _fetch_tencent_inline(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode,
    ) -> pd.DataFrame:
        """Fetch Tencent history and normalise its volume-only schema."""
        adjust_map = {"qfq": "qfq", "hfq": "hfq", "none": ""}
        try:
            raw: pd.DataFrame = ak.stock_zh_a_hist_tx(
                symbol=_tencent_symbol(symbol),
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust_map.get(adjust, "qfq"),
                timeout=10,
            )
        except Exception as exc:
            raise UpstreamUnavailableError(f"Tencent history failed for {symbol}") from exc

        if raw is None or raw.empty:
            return _empty_ohlcv()

        required = ["date", "open", "high", "low", "close"]
        missing = [column for column in required if column not in raw.columns]
        if missing:
            raise UpstreamUnavailableError(f"Tencent history schema missing: {', '.join(missing)}")

        result = raw[required].copy()
        if "volume" in raw.columns:
            result["volume"] = raw["volume"]
            result["amount"] = raw["amount"] if "amount" in raw.columns else float("nan")
        elif "amount" in raw.columns:
            # AkShare's Tencent endpoint names trading volume (hands) ``amount``.
            result["volume"] = raw["amount"]
            result["amount"] = float("nan")
        else:
            raise UpstreamUnavailableError("Tencent history schema has no volume field")

        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        for column in ["open", "high", "low", "close", "volume", "amount"]:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[["date", "open", "high", "low", "close", "volume"]].isna().any().any():
            raise UpstreamUnavailableError("Tencent history returned invalid required values")
        return result.sort_values("date").drop_duplicates(subset="date", keep="last")

    @staticmethod
    def _fetch_market_overview(trade_date: date) -> dict[str, object]:
        result = upstream.run("spot", {"date": trade_date.isoformat()},
                              timeout=_OVERVIEW_TIMEOUT_SECONDS, attempts=_OVERVIEW_ATTEMPTS)
        if not isinstance(result, dict) or not isinstance(result.get("tradeDate"), str):
            raise ValueError("invalid market overview worker output")
        observed = date.fromisoformat(result["tradeDate"])
        if observed > trade_date:
            raise ValueError("future market snapshot")
        unavailable = result.setdefault("unavailableMetrics", [])
        payload = {"date": observed.isoformat()}

        def optional(stage, data):
            try:
                return upstream.run(stage, data, timeout=12)
            except RuntimeError:
                logger.warning("optional overview stage unavailable: %s %s", stage, data)
                return None

        # Separate deadlines: a slow index cannot discard the completed market snapshot.
        with ThreadPoolExecutor(max_workers=3) as pool:
            north = pool.submit(optional, "northbound", payload)
            indices = [(symbol, pool.submit(optional, "index", {
                **payload, "symbol": symbol, "name": name,
            })) for symbol, name in INDEX_SYMBOLS]
            result["northboundNetCny"] = north.result()
            if result["northboundNetCny"] is None:
                unavailable.append("northboundNetCny")
            result["indices"] = []
            for symbol, task in indices:
                value = task.result()
                if value is None:
                    unavailable.append(f"index:{symbol}")
                else:
                    result["indices"].append(value)
        return result

    # ------------------------------------------------------------------
    # 兼容旧入口
    # ------------------------------------------------------------------

    def stock_history(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        return self.history(
            symbol,
            date.fromisoformat(start_date),
            date.fromisoformat(end_date),
            adjust,  # type: ignore[arg-type]
        )


# ------------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------------


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
