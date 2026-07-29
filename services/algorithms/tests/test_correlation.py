from datetime import date

import pandas as pd
import pytest

from quant_platform.analytics.correlation import CorrelationAnalyzer
from quant_platform.models import AdjustMode, CorrelationRequest, DataStatus


class FakeProvider:
    """返回两个资产有重叠日期、一个资产独立日期的假数据。"""

    def _make_ohlcv(self, close_values: list[float], start: date) -> pd.DataFrame:
        dates = pd.date_range(start=start, periods=len(close_values), freq="B")
        return pd.DataFrame({
            "date": dates,
            "open": [c - 0.1 for c in close_values],
            "high": [c + 0.2 for c in close_values],
            "low": [c - 0.2 for c in close_values],
            "close": close_values,
            "volume": [10000] * len(close_values),
            "amount": [c * 10000 for c in close_values],
        })

    def list_assets(self, query=None, asset_type=None, limit=50):
        return []

    def history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: AdjustMode = "qfq",
    ) -> pd.DataFrame:
        if symbol == "510300":
            # 100, 101, ..., 119
            return self._make_ohlcv([100.0 + i for i in range(20)], start_date)
        if symbol == "510500":
            # 50, 51, ..., 69
            return self._make_ohlcv([50.0 + i for i in range(20)], start_date)
        if symbol == "159915":
            # 只有最后 5 天有重叠
            start = start_date + pd.tseries.offsets.BDay(15)
            return self._make_ohlcv([30.0 + i for i in range(5)], start)
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])

    def status(self) -> DataStatus:
        return DataStatus(
            status="ready",
            source="fake",
            asset_count=3,
            latest_trade_date=None,
            updated_at=None,
        )


class TestCorrelation:
    def test_basic_two_assets(self):
        analyzer = CorrelationAnalyzer(FakeProvider())
        result = analyzer.calculate(CorrelationRequest(
            symbols=("510300", "510500"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ))
        assert result.symbols == ("510300", "510500")
        assert result.observation_count > 0
        assert len(result.matrix) == 2
        assert len(result.matrix[0]) == 2
        # 对角线为 1
        assert abs(result.matrix[0][0] - 1.0) < 1e-9
        assert abs(result.matrix[1][1] - 1.0) < 1e-9
        # 对称
        assert abs(result.matrix[0][1] - result.matrix[1][0]) < 1e-9

    def test_three_assets_partial_overlap(self):
        """第三个资产只有最后 5 天有数据重叠。"""
        analyzer = CorrelationAnalyzer(FakeProvider())
        result = analyzer.calculate(CorrelationRequest(
            symbols=("510300", "510500", "159915"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ))
        assert len(result.symbols) == 3
        # 共同日期只有 5 个
        assert result.observation_count == 4  # 5 天 → 4 个收益率

    def test_fewer_than_two_symbols(self):
        analyzer = CorrelationAnalyzer(FakeProvider())
        with pytest.raises(ValueError):
            analyzer.calculate(CorrelationRequest(
                symbols=("510300",),
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            ))

    def test_no_data_returns_zero_matrix(self):
        analyzer = CorrelationAnalyzer(FakeProvider())
        result = analyzer.calculate(CorrelationRequest(
            symbols=("999999", "888888"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 10),
        ))
        assert result.observation_count == 0
        assert all(v == 0.0 for row in result.matrix for v in row)
