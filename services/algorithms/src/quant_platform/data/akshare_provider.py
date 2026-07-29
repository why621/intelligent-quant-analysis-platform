from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import override

import akshare as ak
import pandas as pd

from quant_platform.models import AdjustMode, Asset, AssetType, DataState, DataStatus

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

_CACHE_DIR = Path(__file__).resolve().parents[3] / "tests" / ".cache" / "akshare"

INDEX_SYMBOLS = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
    ("000688", "科创50"),
    ("000300", "沪深300"),
    ("000905", "中证500"),
]


def _today() -> date:
    return date.today()


class AkShareMarketDataProvider:
    """AkShare 数据适配器——算法模块中唯一允许了解 AkShare API 细节的类。"""

    def __init__(self) -> None:
        self._assets: dict[str, Asset] = {
            a["symbol"]: Asset(
                symbol=a["symbol"],
                name=a["name"],
                asset_type=a["asset_type"],  # type: ignore[arg-type]
                exchange=a["exchange"],  # type: ignore[arg-type]
            )
            for a in _DEFAULT_UNIVERSE
        }
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
            result = [
                a
                for a in result
                if q in a.symbol or q in a.name.lower()
            ]
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
        adjust_map = {"qfq": "qfq", "hfq": "hfq", "none": ""}
        period = "daily"

        try:
            raw: pd.DataFrame = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=adjust_map.get(adjust, "qfq"),
            )
        except Exception:
            return _empty_ohlcv()

        if raw.empty:
            return _empty_ohlcv()

        raw = raw.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
        )
        raw["date"] = pd.to_datetime(raw["date"]).dt.date
        raw = raw.sort_values("date").drop_duplicates(subset="date")

        needed = ["date", "open", "high", "low", "close", "volume", "amount"]
        existing = [c for c in needed if c in raw.columns]
        result = raw[existing].copy()

        for c in needed:
            if c not in result.columns:
                result[c] = 0.0 if c != "date" else None

        result = result[needed]
        result["date"] = pd.to_datetime(result["date"])
        return result

    def status(self) -> DataStatus:
        """返回缓存的日更状态。

        update_daily() 调用后，status 才会变为 ready。
        """
        return self._status

    def update_daily(self) -> DataStatus:
        """收盘后调用一次，梳理所有资产的行情并更新状态。

        网络失败时保留上次成功数据，状态标记为 stale。
        """
        try:
            latest_date: date | None = None
            success = 0
            for sym in self._assets:
                try:
                    df = self.history(sym, _today() - timedelta(days=365), _today())
                    if not df.empty:
                        success += 1
                        max_date = df["date"].max()
                        if hasattr(max_date, "date"):
                            max_date = max_date.date()  # type: ignore[union-attr]
                        if latest_date is None or max_date > latest_date:  # type: ignore[operator]
                            latest_date = max_date  # type: ignore[assignment]
                except Exception:
                    continue

            self._status = DataStatus(
                status="ready" if success > 0 else "failed",
                source="AkShare",
                asset_count=len(self._assets),
                latest_trade_date=latest_date,
                updated_at=datetime.now(),
                message=f"已更新 {success}/{len(self._assets)} 个资产" if success else "全部资产拉取失败",
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

        # 涨停 / 跌停：涨跌幅 >= 9.9% 或 <= -9.9%（粗略估计，A 股不同板块涨停板不同）
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
                idx_df = ak.stock_zh_index_daily(symbol=f"sh{idx_sym}" if idx_sym.startswith("0") else f"sz{idx_sym}")
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
