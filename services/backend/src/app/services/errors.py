from __future__ import annotations


class ServiceError(Exception):
    """服务层业务错误：由路由层捕获并转换为契约错误响应。"""

    code = "INTERNAL_ERROR"
    status = 500
    message = "未预期的服务端错误"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.details = details or {}


class AssetNotFoundError(ServiceError):
    code = "ASSET_NOT_FOUND"
    status = 404
    message = "资产不在维护的资产池中"


class UpstreamUnavailableError(ServiceError):
    code = "UPSTREAM_UNAVAILABLE"
    status = 503
    message = "数据源暂时不可用，请稍后重试"
