from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from time import sleep

import akshare as ak
import pandas as pd

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

# 数据落在仓库根目录 data/processed/（已在 .gitignore 中）
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[5] / "data" / "processed"

_LOOKBACK_DAYS = 400


def _today() -> date:
    return date.today()


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
        resolved_data_dir = data_dir or _DEFAULT_DATA_DIR
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
        cached = self._storage.load(symbol, adjust)
        if not cached.empty:
            lo = pd.Timestamp(start_date)
            hi = pd.Timestamp(end_date)
            if cached["date"].min() <= lo and cached["date"].max() >= hi:
                return cached[(cached["date"] >= lo) & (cached["date"] <= hi)]

        try:
            raw = self._fetch_tencent(symbol, start_date, end_date, adjust)
        except UpstreamUnavailableError:
            if not cached.empty:
                lo = pd.Timestamp(start_date)
                hi = pd.Timestamp(end_date)
                return cached[(cached["date"] >= lo) & (cached["date"] <= hi)]
            raise
        if raw.empty:
            # 缓存有部分数据时，返回能覆盖到的部分
            if not cached.empty:
                lo = pd.Timestamp(start_date)
                hi = pd.Timestamp(end_date)
                return cached[(cached["date"] >= lo) & (cached["date"] <= hi)]
            return _empty_ohlcv()

        # 合并缓存与 API 数据，去重后写回缓存
        if not cached.empty:
            merged = (
                pd.concat([cached, raw], ignore_index=True)
                .drop_duplicates(subset="date")
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

    def update_daily(self) -> DataStatus:
        """Incrementally refresh all assets once after market close."""
        today = _today()
        previous_status = self._status_storage.load(len(self._assets))
        self._status_storage.save(
            status="updating",
            latest_trade_date=previous_status.latest_trade_date,
            message="日更任务进行中",
        )
        available = 0
        refreshed = 0
        upstream_errors = 0
        latest_date: date | None = None

        for symbol in self._assets:
            try:
                cached = self._storage.load(symbol)
                if not cached.empty:
                    available += 1
                    cached_date = cached["date"].max().date()
                    if latest_date is None or cached_date > latest_date:
                        latest_date = cached_date
                    start = cached_date + timedelta(days=1)
                else:
                    start = today - timedelta(days=_LOOKBACK_DAYS)

                if start > today:
                    continue

                try:
                    frame = self._fetch_tencent(symbol, start, today, "qfq")
                finally:
                    if self._request_interval_seconds:
                        sleep(self._request_interval_seconds)

                if frame.empty:
                    continue

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
                if latest_date is None or merged_date > latest_date:
                    latest_date = merged_date
            except Exception:
                upstream_errors += 1

        try:
            self.refresh_market_overview()
        except (OSError, UpstreamUnavailableError, ValueError):
            upstream_errors += 1

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
        )
        return self._status_storage.load(total)

    def market_overview(self, trade_date: date | None = None) -> dict[str, object]:
        """Return the local snapshot; call the live provider only on a cold cache."""
        cached = self._overview_storage.load()
        if trade_date is not None:
            requested = trade_date.isoformat()
            if cached is None or cached.get("tradeDate") != requested:
                raise ValueError("the requested trade date is not available in the local cache")
        if cached is not None:
            return dict(cached)
        return self.refresh_market_overview()

    def refresh_market_overview(self) -> dict[str, object]:
        """Refresh and persist the market snapshot; intended for the daily CLI."""
        overview = self._fetch_market_overview(_today())
        self._overview_storage.save(overview)
        return overview

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _fetch_tencent(
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

    def _fetch_market_overview(self, trade_date: date) -> dict[str, object]:
        try:
            spot_df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            raise UpstreamUnavailableError("market overview upstream failed") from exc

        if spot_df is None or spot_df.empty or "涨跌幅" not in spot_df:
            raise UpstreamUnavailableError("market overview upstream returned invalid data")

        change = pd.to_numeric(spot_df["涨跌幅"], errors="coerce").dropna()
        advancing = int(change.gt(0).sum())
        declining = int(change.lt(0).sum())
        unchanged = int(change.eq(0).sum())
        limit_up = int(change.ge(9.9).sum())
        limit_down = int(change.le(-9.9).sum())
        turnover = (
            float(pd.to_numeric(spot_df["成交额"], errors="coerce").fillna(0).sum())
            if "成交额" in spot_df.columns
            else 0.0
        )

        northbound = None
        try:
            northbound_frame = ak.stock_hsgt_hist_em(symbol="北向资金")
            if not northbound_frame.empty:
                northbound_frame["日期"] = pd.to_datetime(northbound_frame["日期"], errors="coerce")
                northbound_frame = northbound_frame[
                    northbound_frame["日期"] <= pd.Timestamp(trade_date)
                ].sort_values("日期")
                net_buy = pd.to_numeric(
                    northbound_frame["当日成交净买额"], errors="coerce"
                ).dropna()
                if not net_buy.empty:
                    # AkShare returns this field in 100 million CNY.
                    northbound = float(net_buy.iloc[-1]) * 100_000_000
        except Exception:
            pass

        latest_index_date: date | None = None
        indices: list[dict[str, object]] = []
        for index_symbol, index_name in INDEX_SYMBOLS:
            try:
                prefix = "sh" if index_symbol.startswith("0") else "sz"
                index_frame = ak.stock_zh_index_daily(symbol=f"{prefix}{index_symbol}")
                index_frame["date"] = pd.to_datetime(index_frame["date"], errors="coerce")
                index_frame = index_frame[index_frame["date"] <= pd.Timestamp(trade_date)]
                index_frame = index_frame.sort_values("date")
                if index_frame.empty:
                    continue
                snapshot_date = index_frame.iloc[-1]["date"].date()
                if latest_index_date is None or snapshot_date > latest_index_date:
                    latest_index_date = snapshot_date
                latest_close = float(index_frame.iloc[-1]["close"])
                previous_close = (
                    float(index_frame.iloc[-2]["close"]) if len(index_frame) >= 2 else latest_close
                )
                change_pct = (latest_close / previous_close - 1) * 100 if previous_close else 0.0
                indices.append(
                    {
                        "symbol": index_symbol,
                        "name": index_name,
                        "close": latest_close,
                        "changePct": change_pct,
                    }
                )
            except Exception:
                continue

        return {
            "tradeDate": (latest_index_date or trade_date).isoformat(),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "limitUp": limit_up,
            "limitDown": limit_down,
            "turnoverCny": turnover,
            "northboundNetCny": northbound,
            "indices": indices,
        }

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
