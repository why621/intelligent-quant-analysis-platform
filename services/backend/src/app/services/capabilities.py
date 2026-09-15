"""Read-only module data preflight against the SAME immutable research snapshot.

A ready result confirms data coverage, not profitability or numerical suitability
of every strategy parameter. Execution retains its own complete validation.
"""

from datetime import date, timedelta

import pandas as pd
from quant_platform import allocation as allocation_module
from quant_platform.data.akshare_provider import UpstreamUnavailableError
from quant_platform.data.calendar import CalendarUnavailableError, latest_session
from quant_platform.ranking import StrategyRankingService, _start_date

from app.services.research_dates import research_read


def check(provider, payload):
    module = payload["module"]
    if not hasattr(provider, "publication_context"):
        return {
            "module": module,
            "state": "unknown",
            "dataContext": None,
            "startDate": None,
            "endDate": None,
            "issues": [],
            "message": "当前数据模式不支持离线预检，请以实际计算结果为准",
        }
    with research_read(provider) as context:
        end = provider.end
        start = provider.start
        symbols = payload.get("symbols", [])
        if module in {"correlation", "backtest"}:
            start = date.fromisoformat(payload["startDate"])
            end = date.fromisoformat(payload["endDate"])
        elif module == "ranking":
            start = _start_date(end, payload.get("period", "30d")) - timedelta(days=90)
            symbols = [StrategyRankingService._BENCHMARK_SYMBOL]
        elif module == "allocation":
            start = end - timedelta(days=allocation_module.AllocationService._LOOKBACK_DAYS)
        result = {
            "module": module,
            "state": "ready",
            "dataContext": context,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "issues": [],
            "message": "数据覆盖检查通过；计算时仍校验参数及有效样本",
        }

        def issue(symbol, code, message):
            result["issues"].append({"symbol": symbol, "code": code, "message": message})
            result["state"] = "unavailable"

        if module == "overview":
            overview = provider.market_overview()
            if overview.get("partial") or not overview.get("indices"):
                result.update(state="partial", message="展示有效股票；缺失行情和指数单独标注")
            return result
        if module == "allocation":
            try:
                required = latest_session(allocation_module._today() - timedelta(days=1))
                allocation_module._next_trading_day(end)
                if end != required:
                    issue(None, "DATA_STALE", "配置需要最近已完成交易日数据，请等待日更")
            except CalendarUnavailableError:
                issue(None, "CALENDAR_UNAVAILABLE", "交易日历尚未覆盖所需日期")
        dependencies = list(symbols)
        if module == "backtest" and payload.get("benchmark"):
            dependencies.append(payload["benchmark"])
        frames = {}
        for symbol in dict.fromkeys(dependencies):
            if symbol not in provider._assets and symbol != "index:CSI:000300":
                issue(symbol, "ASSET_NOT_FOUND", "资产不在当前研究目录")
                continue
            if start < provider.start or end > provider.end:
                issue(symbol, "DATE_OUT_OF_RANGE", "所需区间（含预热）超出已发布范围，请缩短区间")
                continue
            try:
                frame = provider.history(symbol, start, end)
            except (UpstreamUnavailableError, CalendarUnavailableError):
                issue(symbol, "DATA_GAP", "所需区间有未知缺日或基准未更新；可改用有数据的历史区间")
                continue
            frames[symbol] = frame
            minimum = 10 if module == "allocation" else 3 if module == "correlation" else 2
            if len(frame) < minimum:
                issue(symbol, "INSUFFICIENT_HISTORY", f"所需区间不足 {minimum} 条实际行情")
            if module == "allocation" and pd.Timestamp(frame.iloc[-1]["date"]).date() != end:
                issue(
                    symbol, "NO_CURRENT_BAR", "所选资产当日无实际行情，停牌资产暂不能生成当前配置"
                )
        if module == "correlation" and len(frames) == len(symbols):
            common = set.intersection(*(set(pd.to_datetime(f["date"])) for f in frames.values()))
            if len(common) < 3:
                issue(None, "INSUFFICIENT_COMMON_HISTORY", "共同交易日不足，无法计算相关系数")
        if result["issues"]:
            result["message"] = "；".join(dict.fromkeys(i["message"] for i in result["issues"]))
        return result
