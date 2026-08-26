from __future__ import annotations

import numpy as np
import pandas as pd

from quant_platform.interfaces import MarketDataProvider
from quant_platform.models import CorrelationRequest, CorrelationResult


class CorrelationAnalyzer:
    """资产收益率相关性分析。

    MarketDataProvider 通过依赖注入传入，不直接依赖 AkShare。
    """

    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    def calculate(self, request: CorrelationRequest) -> CorrelationResult:
        if len(request.symbols) < 2:
            raise ValueError("symbols 必须包含至少 2 个资产")

        # 拉取各资产的日线
        price_frames: dict[str, pd.DataFrame] = {}
        for sym in request.symbols:
            df = self._provider.history(sym, request.start_date, request.end_date, request.adjust)
            if not df.empty:
                price_frames[sym] = df.set_index("date")["close"]

        if len(price_frames) < 2:
            return CorrelationResult(
                symbols=request.symbols,
                observation_count=0,
                matrix=tuple((0.0,) * len(request.symbols) for _ in request.symbols),
            )

        # 按共同日期对齐
        price_table = pd.DataFrame(price_frames).dropna()

        if price_table.empty or len(price_table) < 2:
            return CorrelationResult(
                symbols=request.symbols,
                observation_count=0,
                matrix=tuple((0.0,) * len(request.symbols) for _ in request.symbols),
            )

        # 收益率
        if request.return_type == "log":
            returns = np.log(price_table / price_table.shift(1))
        else:
            returns = price_table.pct_change()

        returns = returns.dropna()

        # 相关系数矩阵
        corr = returns.corr()

        # 按请求的 symbols 顺序排列
        ordered = [s for s in request.symbols if s in corr.columns]
        corr = corr.loc[ordered, ordered]

        matrix = tuple(
            tuple(float(corr.at[r, c]) for c in corr.columns)
            for r in corr.index
        )

        return CorrelationResult(
            symbols=tuple(ordered),
            observation_count=len(returns),
            matrix=matrix,
        )
