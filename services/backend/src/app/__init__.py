from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, g, request
from quant_platform.allocation import AllocationService as AlgorithmAllocationService
from quant_platform.analytics.correlation import CorrelationAnalyzer
from quant_platform.backtesting.engine import BacktestEngine
from quant_platform.data.akshare_provider import AkShareMarketDataProvider
from quant_platform.ranking import StrategyRankingService

from app.api.routes import api
from app.services.allocation import AllocationService
from app.services.analytics import CorrelationService
from app.services.backtests import BacktestJobStore, BacktestService, BacktestWorker
from app.services.data import MarketDataService
from app.services.ranking import RankingService
from app.services.strategies import StrategyCatalogService

BACKTEST_DB_DEFAULT = str(Path(__file__).resolve().parents[2] / "var" / "backtests.db")

__version__ = "0.1.0"


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    """Create and configure the Flask application."""
    application = Flask(__name__)
    application.config.from_mapping(
        APP_VERSION=__version__,
        ALLOWED_ORIGINS=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173"),
    )
    if test_config:
        application.config.update(test_config)

    allowed_origins = {
        origin.strip()
        for origin in str(application.config["ALLOWED_ORIGINS"]).split(",")
        if origin.strip()
    }

    @application.before_request
    def attach_trace_id() -> None:
        g.trace_id = f"req_{uuid4().hex[:16]}"

    @application.after_request
    def add_cors_headers(response: Response) -> Response:
        request_origin = request.headers.get("Origin", "")
        if request_origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Vary"] = "Origin"
        return response

    application.register_blueprint(api, url_prefix="/api")

    # 装配服务：路由通过 current_app.extensions 获取服务。
    # provider 复用同一个实例，保证所有接口共享同一份缓存。
    provider = AkShareMarketDataProvider()
    application.extensions["market_data_service"] = MarketDataService(provider)

    strategy_catalog = StrategyCatalogService()
    application.extensions["strategy_catalog_service"] = strategy_catalog

    application.extensions["correlation_service"] = CorrelationService(
        CorrelationAnalyzer(provider)
    )

    # 回测任务存储：测试用独立临时目录，避免污染 var/ 下的真实任务库。
    if application.config.get("TESTING"):
        db_path = os.path.join(tempfile.mkdtemp(prefix="backtest-db-"), "backtests.db")
    else:
        db_path = os.environ.get("BACKTEST_DB_PATH", BACKTEST_DB_DEFAULT)
    backtest_store = BacktestJobStore(db_path)
    # 回测引擎共享单例：无状态设计（run 只读 provider/策略注册表），
    # worker 线程跑回测与 ranking 请求同步跑引擎互不干扰。
    engine = BacktestEngine(provider, strategy_catalog.registry())
    backtest_service = BacktestService(
        backtest_store,
        strategy_catalog,
        provider,
        engine,
    )
    application.extensions["backtest_service"] = backtest_service
    application.extensions["ranking_service"] = RankingService(
        StrategyRankingService(engine),
        provider,
        strategy_catalog,
    )
    # 配置建议：算法组服务只依赖 provider（只读共享）与策略注册表，无状态
    # 多线程安全；日期锚点由算法组内部决定（墙钟），后端按约定透传。
    application.extensions["allocation_service"] = AllocationService(
        AlgorithmAllocationService(provider, strategy_catalog.registry()),
        strategy_catalog,
    )
    if not application.config.get("TESTING"):
        BacktestWorker(backtest_store, backtest_service).start()
    return application
