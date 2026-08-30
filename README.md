# 智能量化分析平台

面向市场洞察、资产相关性分析、策略回测、策略评估与资产配置的协作式量化分析平台。本仓库采用 monorepo，统一保存 Vue 前端、Flask 后端、Python 算法模块、接口契约与测试。

截至 2026-08-30，传统策略最小闭环已经完成：前端通过真实 API 获取数据，后端已实现 OpenAPI 中的全部接口，算法模块已实现行情缓存、相关性、两个传统策略、回测、排行和次日模拟配置。DQN、PPO 与多智能体策略仍属于后续规划；生产环境部署、定时任务、监控和备份尚需补齐。

## 仓库结构

    .
    ├── apps/frontend/            # Vue 3 + Vite + ECharts 前端
    ├── services/backend/         # Flask API、校验、异步任务和 SQLite 持久化
    ├── services/algorithms/      # AkShare 数据、策略、回测、排行和配置算法
    ├── packages/contracts/       # OpenAPI 与共享 Schema
    ├── docs/                     # 架构、契约、实施与答辩说明
    ├── .github/workflows/        # 前端、后端、算法 CI 与 Pages 部署
    └── package.json              # 前端 workspace 命令

模块职责见 [架构说明](docs/architecture.md)。前端只调用后端 API，不直接调用 AkShare 或算法模块；跨模块字段以 [OpenAPI 契约](packages/contracts/openapi.yaml) 为准。

## 本地运行

环境要求：Python 3.11+、Node.js ^20.19.0 或 >=22.12.0、npm 10+。

### 1. 安装 Python 模块

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/algorithms[dev]"
python -m pip install -e "services/backend[dev]"
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。

### 2. 初始化或更新行情缓存

```bash
quant-data-update
# 或 python -m quant_platform.cli
```

运行数据保存在 `data/processed/`，包括 `market_data.db` 和 `market_overview.json`；该目录已被 Git 忽略。

### 3. 启动后端

```bash
cp services/backend/.env.example services/backend/.env
quant-backend
curl http://127.0.0.1:8000/api/health
```

### 4. 启动前端

```bash
npm install
cp apps/frontend/.env.example apps/frontend/.env.local
npm run dev:frontend
```

开发服务器默认将 `/api` 代理到 `http://localhost:8000`。生产构建使用：

```bash
npm run build:frontend
```

## 测试与检查

```bash
ruff check services/algorithms
pytest services/algorithms
ruff check services/backend
pytest services/backend
npm run build:frontend
```

测试默认不访问真实网络；涉及 AkShare 的网络用例需在可联网环境单独执行。

## 当前状态

- [x] 前端五个业务模块及真实 API 客户端
- [x] OpenAPI 契约与统一错误结构
- [x] 全部契约路径的 Flask 后端实现
- [x] 30–50 个 A 股/ETF 资产池与 AkShare/Tencent 行情适配
- [x] SQLite 行情缓存、旧 CSV 迁移和数据状态管理
- [x] 相关性、均线交叉、动量反转和无未来函数回测
- [x] SQLite 异步回测任务、策略排行和次日模拟配置
- [x] 前端、后端、算法 CI 与 GitHub Pages 静态前端部署
- [ ] 云服务器上的 API 部署、收盘后定时更新、监控和备份
- [ ] DQN、PPO、多智能体策略
- [ ] 面向实盘的权限、审计、独立风控和人工确认

## 部署边界

GitHub Pages 只能托管静态前端，不能运行 Flask、SQLite 或常驻任务。完整部署需要在云服务器、容器平台或其他 Python 运行环境启动后端，并让前端通过 `VITE_API_BASE_URL` 连接该 API；收盘后数据更新需由 cron 或 systemd timer 独立调度。

## 团队协作

1. 从最新 `main` 创建短期功能分支，不直接向 `main` 提交。
2. 接口变化必须在同一 PR 中同步修改 OpenAPI、实现、测试和调用方。
3. PR 至少由一名相关模块成员审阅，CI 通过后再合并。
4. 生产密钥、账户信息、数据库和真实行情缓存不得提交到仓库。

完整规范见 [贡献指南](CONTRIBUTING.md) 与 [团队协作规范](docs/team-workflow.md)。

## 风险说明

本项目仅用于教学与研究，不构成投资建议，也不连接券商或提交真实订单。AkShare 和其上游数据源可能临时不可用；系统会优先使用最后一次成功缓存，并通过 `/api/data/status` 暴露 `ready/updating/stale/failed` 状态。算法输出、回测结果与历史收益不能保证未来表现。
