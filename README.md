# 智能量化分析平台

面向市场洞察、资产相关性分析、策略回测、策略评估与资产配置的协作式量化分析平台。本仓库采用 monorepo：前端、后端、算法和接口契约保存在同一处，团队成员可以通过 GitHub 分支和 Pull Request 独立开发。

当前可运行部分是 Vue 前端，页面使用 mock 数据。后端与算法目录已预留，等待团队按接口契约接入。

## 仓库结构

    .
    ├── apps/
    │   └── frontend/              # Vue 3 + Vite + ECharts 前端
    ├── services/
    │   ├── backend/               # HTTP API、鉴权、任务编排和持久化
    │   └── algorithms/            # 数据、因子、策略、回测、风控和组合优化
    ├── packages/
    │   └── contracts/             # OpenAPI、JSON Schema 等共享契约
    ├── docs/
    │   ├── api-contract.md        # 当前接口契约草案
    │   └── architecture.md        # 模块边界和调用关系
    ├── .github/workflows/         # CI 与 GitHub Pages 自动部署
    ├── CONTRIBUTING.md            # 分支、提交和 PR 协作约定
    └── package.json               # 前端 workspace 统一命令

模块职责和推荐内部结构见 docs/architecture.md 与各模块目录。不要把后端业务逻辑放进前端，也不要让前端直接调用算法模块；统一通过后端 API 与任务接口衔接。

## 运行前端

环境要求：Node.js ^20.19.0 或不低于 22.12.0，npm 不低于 10.0.0。

    npm install
    npm run dev:frontend

构建和预览：

    npm run build:frontend
    npm run preview:frontend

本地连接后端时：

    cp apps/frontend/.env.example apps/frontend/.env.local

## GitHub 托管范围

- GitHub 仓库：托管前端、后端、算法、测试、文档和版本历史。
- GitHub Actions：每次提交或 Pull Request 自动验证前端构建。
- GitHub Pages：自动发布静态前端演示站。
- 后端与算法运行：GitHub Pages 不能运行 Python、数据库或常驻任务；后续需要部署到云服务器、容器平台或 Serverless 平台，再通过 VITE_API_BASE_URL 连接。

首次推送后，在仓库 Settings → Pages → Build and deployment → Source 中选择 GitHub Actions。之后 main 分支中的前端变更会触发自动发布。

## 团队协作

1. 从 main 创建短期功能分支，不直接向 main 提交。
2. 分别在 apps/frontend、services/backend、services/algorithms 内修改对应模块。
3. 如接口或数据结构发生变化，必须同步更新 docs/api-contract.md 或 packages/contracts。
4. 推送分支并创建 Pull Request，至少由一名相关模块成员审阅。
5. CI 通过后合并；生产密钥、券商密钥、数据库地址和真实交易数据不得提交到仓库。

完整规范见 CONTRIBUTING.md。

## 当前状态

- [x] 前端可本地运行和构建
- [x] 前后端接口契约草案
- [x] GitHub Actions 前端 CI
- [x] GitHub Pages 自动部署工作流
- [ ] 后端 API 实现
- [ ] 算法服务与回测引擎
- [ ] 数据库、队列和对象存储
- [ ] 真实行情与交易数据接入

## 风险说明

本项目提供研究和工程能力，不构成任何投资建议。算法输出、回测结果与历史收益不能保证未来表现。接入实盘前必须补齐权限控制、审计、风控、数据授权和人工确认流程。
