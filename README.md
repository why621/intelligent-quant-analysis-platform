# 智能量化分析平台

面向市场洞察、资产相关性分析、策略回测、策略评估与资产配置的协作式量化分析平台。本仓库采用 monorepo，统一保存 Vue 前端、Flask 后端、Python 算法模块、接口契约与测试。

## 开发规格入口

自2026-09-07起，新增需求和变更按 [spec.md](spec.md) 登记，并联动 [PRD.md](PRD.md)、[design.md](design.md) 和 [task.md](task.md)。新基线区分当前实现、历史部署观测、沪深300阶段目标与待验证事项；带日期的旧部署记录仅代表对应批次，当前状态以最新总结及上线实录为准。接口字段仍以OpenAPI为准。

## 最新发布状态（2026-10-11，CR065云端已上线，Pages待合并）

本轮新增默认的所选资产买入持有基准、实际买卖点、每日持仓比例和交易成本分项；传统策略改为共享组合资金账户，现金预留与费用进入同一执行口径。买入持有基准采用初始等权价格持有，不再平衡、不计成本，页面明确披露该差异；旧任务未保存的账户与费用字段显示“未记录”。

五模块通过研究草稿衔接：市场发布截止日可设置研究区间，相关性资产/日期默认同步回测，回测参数、资金、现金预留及费用默认同步模拟重放。下游手动修改后可恢复跟随，联动不自动提交计算、不改写旧结果。排行仍是固定510300代表资产，新增实际评价起止、前置运行历史与费用说明，可显式载入回测继续研究。

新的多资产RL组合环境与训练入口仅用于研究和小规模CPU烟测，尚未接入网页策略目录，未发布新模型，也未证明收益有效性。原有已发布单资产模型继续按旧模式及已记录训练范围披露；模拟配置不静默启用不受支持的AI策略。CR065网站/API已部署[云站](https://43.161.223.91/)，源码已推送[PR #47](https://github.com/why621/intelligent-quant-analysis-platform/pull/47)，Pages待合并。未采集新行情，四模型/旧任务/行情与07:30日更保持。

本轮已完成596项算法/后端、105项前端测试，云隔离7任务、实际HTTPS浏览器33项及最终手机图例修正验收。详见[CR065上线与需求复核](docs/cr065-deployment-2026-10-11.md)及[本地验收](docs/cr065-validation-2026-10-11.md)；云站与Pages分别记录，CPU烟测不替代正式训练或绩效验证。

## 上一版上线记录（2026-10-02）

平台接入固定300只沪深300成分股及27只ETF，提供五个研究模块。CR062已部署PPO、DQN、SAC、TD3四个实验模型；本批模型仅支持510300，预热140根、至少142根行情。训练为2015–2018年上半年，验证至2021年末，理论样本外下限2022-01-01；实际网页研究仍受已发布行情范围限制。未证明长期超额收益或跨资产通用性，训练/回评费用差异明确披露，不连接实盘。

CR064全页面柔和光影、紧凑布局和适量动效已部署[云端网页](https://43.161.223.91/)。PR45已合并main 2ca1d76，[GitHub Pages](https://why621.github.io/intelligent-quant-analysis-platform/)已发布并通过实际桌面/手机及跨域接口验收。每天北京时间07:30持续日更保留。

[上次上线交接](docs/session-handoff-2026-10-02.md) · [CR064 UI与部署验收](docs/cr064-ui-density-2026-10-02.md) · [CR062模型上线](docs/cr062-model-deployment-2026-10-01.md)。这些记录描述对应日期的验收结果，不代表本轮重新验证了线上状态。

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

按 .env.example 设置 VITE_API_PROXY_TARGET 后，开发服务器将 `/api` 代理到 `http://localhost:8000`。生产构建使用：

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
- [x] 固定300只沪深300成分股、27只ETF及独立沪深300价格指数接入
- [x] SQLite 行情缓存、旧 CSV 迁移和数据状态管理
- [x] 相关性、均线交叉、动量反转和无未来函数回测
- [x] SQLite 异步回测任务、策略排行和次日模拟配置
- [x] 前端、后端、算法 CI 与 GitHub Pages 静态前端部署
- [x] HTTPS云API、每天07:30持续日更、健康检查与SQLite备份恢复
- [x] 已部署PPO、DQN、SAC、TD3的510300单资产网页实验回测；仍为experimental
- [x] 510300代表资产的四种RL样本外实验排行及未参与原因
- [x] CR065本地传统策略共享账户、默认买入持有对照、交易/持仓/成本解释及模块草稿联动（尚未发布）
- [ ] 新多资产RL模型的正式训练、绩效验证、网页集成与发布；本地研究入口/CPU烟测不等于完成这些阶段
- [ ] 多智能体策略、RL配置、跨资产长期绩效验证
- [ ] 长期运行可靠性、完善的故障通知与监控
- [ ] 面向实盘的权限、审计、独立风控和人工确认

## 部署边界

GitHub Pages 只能托管静态前端，不能运行 Flask、SQLite 或常驻任务。当前后端已部署到现有云服务器，Pages通过 `VITE_API_BASE_URL` 连接HTTPS API；持续日更由systemd timer每天Asia/Shanghai 07:30调度。启用定时器不等同每次采集成功；长期稳定性须按实际运行记录判断。RL需额外安装算法 `[rl]` 依赖并配置已验证模型清单，权重不随Git仓库分发，详见[部署实录](docs/cr049-rl-four-web-2026-09-20.md)。

## 团队协作

1. 从最新 `main` 创建短期功能分支，不直接向 `main` 提交。
2. 接口变化必须在同一 PR 中同步修改 OpenAPI、实现、测试和调用方。
3. PR 至少由一名相关模块成员审阅，CI 通过后再合并。
4. 生产密钥、账户信息、数据库和真实行情缓存不得提交到仓库。

完整规范见 [贡献指南](CONTRIBUTING.md) 与 [团队协作规范](docs/team-workflow.md)。

## 风险说明

本项目仅用于教学与研究，不构成投资建议，也不连接券商或提交真实订单。AkShare 和其上游数据源可能临时不可用；系统会优先使用最后一次成功缓存，并通过 `/api/data/status` 暴露 `ready/updating/stale/failed` 状态。算法输出、回测结果与历史收益不能保证未来表现。

2026-09-20 CR050：云端排行榜已纳入四种RL，按相同评价窗口比较，保持实验标识；[排行实现与验收](docs/cr050-rl-ranking-2026-09-20.md)。PR #35已合并，Pages排行说明已发布；合并提交的四项CI全部通过。
