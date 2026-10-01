"""只读网络探测：三个 ETF 在腾讯源缺失的交易日，其他源是否同样无K线。

用途：判定 510500（2015-04-13/14）与 159915（2021-02-08）的缺口是
「个券真实停牌」还是「腾讯源数据缺口」，为研究缓存回填选择处理方式。
只打印证据，不断言盈亏，不写任何缓存。跑法：
    PYTHONUTF8=1 python -m pytest tests/test_etf_missing_sessions_probe.py \
        -o addopts="-q" -m network
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

pytestmark = pytest.mark.network

CASES = (
    ("510500", date(2015, 4, 10), date(2015, 4, 15), {date(2015, 4, 13), date(2015, 4, 14)}),
    ("159915", date(2021, 2, 5), date(2021, 2, 10), {date(2021, 2, 8)}),
)


def _fmt(days) -> str:
    return ",".join(sorted(d.isoformat() for d in days)) or "（无）"


@pytest.mark.parametrize("symbol,start,end,missing", CASES)
def test_cross_source_coverage_of_missing_sessions(symbol, start, end, missing, capsys):
    import akshare as ak

    em = ak.fund_etf_hist_em(
        symbol=symbol, period="daily",
        start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"),
        adjust="qfq",
    )
    em_days = set(pd.to_datetime(em["日期"]).dt.date)

    sina = ak.fund_etf_hist_sina(symbol=f"sz{symbol}" if symbol.startswith("1") else f"sh{symbol}")
    sina_days = set(pd.to_datetime(sina["date"]).dt.date)
    sina_days = {d for d in sina_days if start <= d <= end}

    tx = ak.stock_zh_a_hist_tx(
        symbol=f"sz{symbol}" if symbol.startswith("1") else f"sh{symbol}",
        start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), adjust="qfq",
    )
    tx_days = set(pd.to_datetime(tx["date"]).dt.date)

    with capsys.disabled():
        print(f"\n== {symbol} 腾讯缺失日: {_fmt(missing)}")
        print(f"   东财 qfq 有K线的日期: {_fmt(em_days)}")
        print(f"   新浪 有K线的日期:     {_fmt(sina_days)}")
        print(f"   腾讯 qfq 有K线的日期: {_fmt(tx_days)}")
        for day in sorted(missing):
            verdict = {
                "eastmoney": day in em_days,
                "sina": day in sina_days,
                "tencent": day in tx_days,
            }
            kind = "源缺口" if any(verdict.values()) else "全源无K线（疑似停牌）"
            print(f"   {day.isoformat()}: {verdict} -> {kind}")
