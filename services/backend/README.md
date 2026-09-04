# 后端服务

`services/backend` 是 Flask API 服务，负责契约校验、行情和算法调用、异步回测任务以及 SQLite 持久化。当前已实现 [OpenAPI 契约](../../packages/contracts/openapi.yaml) 中的全部路径。

## 接口状态

| 方法 | 路径 | 实现 |
| --- | --- | --- |
| GET | `/api/health` | 服务健康检查 |
| GET | `/api/data/status` | 行情缓存状态 |
| GET | `/api/assets` | 资产列表与筛选 |
| GET | `/api/assets/{symbol}/history` | 历史行情 |
| GET | `/api/market/overview` | 市场概览 |
| POST | `/api/analysis/correlation` | 相关性分析 |
| GET | `/api/strategies` | 策略目录 |
| GET | `/api/strategies/ranking` | 策略排行 |
| POST | `/api/backtests` | 创建异步回测 |
| GET | `/api/backtests/{jobId}` | 查询回测状态和结果 |
| POST | `/api/allocations` | 生成次日模拟配置 |

统一错误结构与状态码见 [API 契约说明](../../docs/api-contract.md)。

## 本地运行

建议从仓库根目录创建虚拟环境，并同时安装算法和后端模块：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/algorithms[dev]"
python -m pip install -e "services/backend[dev]"
cp services/backend/.env.example services/backend/.env
quant-backend
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。默认监听 `127.0.0.1:8000`。

后端主要环境变量：

| 变量 | 默认值 |
| --- | --- |
| `FLASK_DEBUG` | `1` |
| `HOST` | `127.0.0.1` |
| `PORT` | `8000` |
| `ALLOWED_ORIGINS` | `http://localhost:5173` |

## 数据与任务

- 行情读取统一经过算法模块的数据提供器，默认使用 `data/processed/market_data.db`。
- 建议首次启动前执行 `quant-data-update` 初始化缓存。
- 回测任务保存到 `services/backend/var/backtests.db`，由后台 worker 原子领取并执行。
- 服务重启后，已排队任务仍保留；运行中断的任务需由运维流程确认后显式重新入队。
- 运行数据库、缓存和环境文件均不得提交 Git。

## 测试

```bash
ruff check services/backend
pytest services/backend
```

测试使用隔离的临时数据库与模拟数据源，默认不会访问真实网络。

## 部署边界

当前实现适合课程演示和单服务部署。生产环境仍需补充进程托管、HTTPS、日志采集、监控告警、数据库备份和收盘后数据更新调度。GitHub Pages 不能承载此服务。
