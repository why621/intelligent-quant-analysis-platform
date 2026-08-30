from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date

from quant_platform.analytics.correlation import CorrelationAnalyzer
from quant_platform.data.akshare_provider import (
    UpstreamUnavailableError as ProviderUpstreamError,
)
from quant_platform.models import CorrelationRequest

from app.services.errors import InsufficientDataError, UpstreamUnavailableError


class CorrelationService:
    """相关性分析接口的实现：调用算法组 CorrelationAnalyzer 并翻译为契约 JSON。

    算法组的矩阵在极端数据下可能含 NaN（无波动资产、观察日不足），契约声明
    matrix 元素可空，此处把非有限值（NaN/inf）转 null；
    整体数据不足（observation_count < 2）时返回 422 INSUFFICIENT_DATA。
    """

    def __init__(self, analyzer: CorrelationAnalyzer) -> None:
        self._analyzer = analyzer

    def calculate(
        self,
        *,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        adjust: str,
        return_type: str,
    ) -> Mapping[str, object]:
        """返回相关系数矩阵，字段与 contracts/schemas/analytics.yaml#/CorrelationResponse 一致。"""
        request = CorrelationRequest(
            symbols=tuple(symbols),
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,  # type: ignore[arg-type]
            return_type=return_type,  # type: ignore[arg-type]
        )
        try:
            result = self._analyzer.calculate(request)
        except ProviderUpstreamError as exc:
            raise UpstreamUnavailableError(
                details={"capability": "correlation"}
            ) from exc

        if result.observation_count < 2:
            # 契约要求 200 响应里 observationCount >= 2（schema minimum），
            # 数据不足以计算时统一返回错误而不是违约的 200。
            raise InsufficientDataError(
                details={"reason": "有效资产或共同观察交易日不足 2 个"}
            )

        return {
            "symbols": list(result.symbols),
            "observationCount": result.observation_count,
            "matrix": [_serialize_row(row) for row in result.matrix],
        }


def _serialize_row(row: Sequence[float]) -> list[float | None]:
    """把矩阵一行翻译成契约格式：非有限值（NaN/inf）转 null，避免非法 JSON。"""
    return [None if not math.isfinite(value) else value for value in row]
