from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

from quant_platform.data.storage import OHLCVStore
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


class AkShareMarketDataProvider:
    """AkShare 数据适配器——算法模块中唯一允许了解 AkShare API 细节的类。

    history() 优先读取 CSV 缓存，缓存覆盖不了再调用腾讯接口；
    update_daily() 收盘后增量拉取并落盘到 CSV。
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._assets: dict[str, Asset] = {
            a["symbol"]: Asset(
                symbol=a["symbol"],
                name=a["name"],
                asset_type=a["asset_type"],  # type: ignore[arg-type]
                exchange=a["exchange"],  # type: ignore[arg-type]
            )
            for a in _DEFAULT_UNIVERSE
        }
        self._storage = OHLCVStore(data_dir or _DEFAULT_DATA_DIR)
        self._status = DataStatus(
            status="updating",
            source="AkShare",
            asset_count=len(self._assets),
            latest_trade_date=None,
            updated_at=None,
        )

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
        cached = self._storage.load(symbol)
        if not cached.empty:
            lo = pd.Timestamp(start_date)
            hi = pd.Timestamp(end_date)
            if cached["date"].min() <= lo and cached["date"].max() >= hi:
                return cached[(cached["date"] >= lo) & (cached["date"] <= hi)]

        raw = self._fetch_tencent(symbol, start_date, end_date, adjust)
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
        self._storage.save(symbol, merged)

        lo = pd.Timestamp(start_date)
        hi = pd.Timestamp(end_date)
        return merged[(merged["date"] >= lo) & (merged["date"] <= hi)]

    def status(self) -> DataStatus:
        """返回缓存的日更状态。update_daily() 调用后 status 才会变为 ready。"""
        return self._status

    def update_daily(self) -> DataStatus:
        """收盘后调用一次：增量拉取所有资产并落盘 CSV。

        网络失败保留旧数据，状态标记为 stale/failed。
        """
        try:
            today = _today()
            success = 0
            latest_date: date | None = None
            for sym in self._assets:
                try:
                    cached = self._storage.load(sym)
                    if cached.empty:
                        start = today - timedelta(days=_LOOKBACK_DAYS)
                    else:
                        last = cached["date"].max().date()
                        start = last + timedelta(days=1)

                    if start > today:
                        success += 1
                        continue

                    df = self._fetch_tencent(sym, start, today, "qfq")
                    if df.empty:
                        if not cached.empty:
                            success += 1  # 网络失败但旧数据仍可用
                        continue

                    merged = (
                        pd.concat([cached, df], ignore_index=True)
                        .drop_duplicates(subset="date")
                        .sort_values("date")
                    )
                    self._storage.save(sym, merged)
                    success += 1
                    max_date = merged["date"].max().date()
                    if latest_date is None or max_date > latest_date:
                        latest_date = max_date
                except Exception:
                    continue

            if success == 0:
                self._status = DataStatus(
                    status="failed",
                    source="AkShare",
                    asset_count=len(self._assets),
                    latest_trade_date=None,
                    updated_at=datetime.now(),
                    message="全部资产拉取失败",
                )
            elif success < len(self._assets):
                self._status = DataStatus(
                    status="stale",
                    source="AkShare",
                    asset_count=len(self._assets),
                    latest_trade_date=latest_date,
                    updated_at=datetime.now(),
                    message=f"部分更新 {success}/{len(self._assets)} 个资产",
                )
            else:
                self._status = DataStatus(
                    status="ready",
                    source="AkShare",
                    asset_count=len(self._assets),
                    latest_trade_date=latest_date,
                    updated_at=datetime.now(),
                    message=f"已更新 {success}/{len(self._assets)} 个资产",
                )
        except Exception:
            self._status = DataStatus(
                status="failed",
                source="AkShare",
                asset_count=len(self._assets),
                latest_trade_date=None,
                updated_at=datetime.now(),
                message="日更流程异常",
            )
        return self._status

    def market_overview(self, trade_date: date | None = None) -> dict[str, object]:
        """获取市场宽度、指数快照与成交额。"""
        try:
            spot_df = ak.stock_zh_a_spot_em()
        except Exception:
            return _empty_market_overview(trade_date or _today())

        advancing = int(spot_df["涨跌幅"].gt(0).sum())
        declining = int(spot_df["涨跌幅"].lt(0).sum())
        unchanged = int(spot_df["涨跌幅"].eq(0).sum())

        # 涨停 / 跌停：涨跌幅 >= 9.9% 或 <= -9.9%（粗略估计）
        limit_up = int(spot_df["涨跌幅"].ge(9.9).sum())
        limit_down = int(spot_df["涨跌幅"].le(-9.9).sum())

        turnover = float(spot_df["成交额"].sum()) if "成交额" in spot_df.columns else 0.0

        # 北向资金
        northbound = None
        try:
            nb_df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
            if not nb_df.empty:
                nb_df = nb_df.sort_values("date", ascending=False)
                northbound = float(nb_df.iloc[0]["value"])
        except Exception:
            pass

        # 指数快照
        indices: list[dict[str, object]] = []
        for idx_sym, idx_name in INDEX_SYMBOLS:
            try:
                prefix = "sh" if idx_sym.startswith("0") else "sz"
                idx_df = ak.stock_zh_index_daily(symbol=f"{prefix}{idx_sym}")
                if not idx_df.empty:
                    latest = idx_df.sort_values("date").iloc[-1]
                    indices.append({
                        "symbol": idx_sym,
                        "name": idx_name,
                        "close": float(latest["close"]),
                        "changePct": float(latest.get("pct_chg", 0)),
                    })
            except Exception:
                continue

        return {
            "tradeDate": (trade_date or _today()).isoformat(),
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
    # 内部
    # ------------------------------------------------------------------

    def _fetch_tencent(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode,
    ) -> pd.DataFrame:
        """从腾讯接口拉取并规范化为契约列序。"""
        adjust_map = {"qfq": "qfq", "hfq": "hfq", "none": ""}
        try:
            raw: pd.DataFrame = ak.stock_zh_a_hist_tx(
                symbol=_tencent_symbol(symbol),
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust_map.get(adjust, "qfq"),
            )
        except Exception:
            return _empty_ohlcv()

        if raw is None or raw.empty:
            return _empty_ohlcv()

        needed = ["date", "open", "high", "low", "close", "volume", "amount"]
        result = raw[needed].copy()
        result["date"] = pd.to_datetime(result["date"])
        return result.sort_values("date").drop_duplicates(subset="date")

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
    return pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "volume", "amount"]
    )


def _empty_market_overview(trade_date: date) -> dict[str, object]:
    return {
        "tradeDate": trade_date.isoformat(),
        "advancing": 0,
        "declining": 0,
        "unchanged": 0,
        "limitUp": 0,
        "limitDown": 0,
        "turnoverCny": 0.0,
        "northboundNetCny": None,
        "indices": [],
    }
