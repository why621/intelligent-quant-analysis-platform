# 实施与维护指南

更新日期：2026-08-30

本文用于说明当前代码已经完成到什么程度、如何继续推进，以及答辩时如何准确描述工程边界。

## 当前基线

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 前端业务页面 | 已完成 | 市场、相关性、回测、排行和配置均已接入真实 API |
| OpenAPI 契约 | 已完成 | 路径、请求、响应、错误结构已统一 |
| Flask API | 已完成 | 契约中的全部接口均有真实实现 |
| 数据缓存 | 已完成 | SQLite 缓存、增量更新、旧 CSV 迁移和状态接口 |
| 传统策略 | 已完成 | 均线交叉、动量反转、相关性、回测、排行和配置 |
| 异步回测 | 已完成 | SQLite 持久化任务与后台 worker |
| GitHub CI | 已完成 | 前端、后端、算法检查 |
| 静态前端部署 | 已完成 | GitHub Pages；不包含 Flask API |
| 完整线上部署 | 待完成 | 后端、持久卷、调度、监控、备份 |
| 强化学习策略 | 规划中 | DQN、PPO、多智能体尚未实现 |
| 实盘交易 | 不在当前范围 | 无券商连接、下单、账户和实盘风控 |

## 本地联调步骤

### 1. 准备环境

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/algorithms[dev]"
python -m pip install -e "services/backend[dev]"
npm install
```

### 2. 初始化行情

```bash
quant-data-update
```

若第三方数据源暂时失败，可继续使用最后一次成功缓存，但必须在页面和答辩中说明数据时间与状态。

### 3. 启动服务

终端一：

```bash
quant-backend
```

终端二：

```bash
npm run dev:frontend
```

依次检查：

- `GET http://127.0.0.1:8000/api/health`
- `GET http://127.0.0.1:8000/api/data/status`
- 前端首页、相关性、回测、排行和配置流程
- 回测提交后能从 `queued/running` 进入 `succeeded` 或给出可解释的 `failed`

## 提交前验证

```bash
ruff check services/algorithms
pytest services/algorithms
ruff check services/backend
pytest services/backend
npm run build:frontend
git diff --check
```

接口字段变化时，还要人工核对 OpenAPI、后端响应和前端使用字段是否一致。

## 下一阶段工作

### P0：完成可演示的线上闭环

1. 在云服务器或容器平台部署 Flask 后端。
2. 为 `data/processed/` 和 `services/backend/var/` 配置持久卷及备份。
3. 设置 HTTPS、反向代理和严格的 `ALLOWED_ORIGINS`。
4. 在前端构建阶段设置公网 `VITE_API_BASE_URL`。
5. 在交易日收盘后调度 `quant-data-update`。
6. 验证公网环境的五个业务模块和错误降级。

### P1：补齐运维能力

- 结构化日志、请求追踪和任务执行日志。
- 服务、磁盘、数据新鲜度和回测失败率监控。
- 告警联系人、故障处理和恢复演练。
- SQLite 定期备份；规模增长后再评估 PostgreSQL 和独立任务队列。

### P2：扩展策略

在统一数据、成本和评估口径下逐步实现 DQN、PPO 和多智能体策略。每新增策略都必须提供基线对比、无未来函数证明、固定区间回归测试和失败处理，不能只展示单次高收益结果。

## 答辩口径

可以表述为：

> 当前系统已经完成前端、后端、传统量化算法和数据缓存的最小业务闭环。接口契约中的全部 API 均已实现，回测任务可持久化并异步执行。GitHub Pages 目前只部署静态前端；完整线上运行仍需单独部署 Flask 服务、配置数据更新调度、监控和备份。DQN、PPO 和多智能体是后续扩展方向，不属于当前已完成功能。

不要表述为“已支持实盘交易”“Pages 已部署完整后端”或“所有 AI 策略均已完成”。

## 工程问题简答

- 为什么使用 OpenAPI：让前端、后端和算法围绕同一字段契约协作，减少口头约定产生的漂移。
- 为什么需要 SQLite：行情和回测任务需要跨进程重启保留，不能依赖浏览器 mock 或纯内存队列。
- 如何处理数据源失败：保留最后成功缓存、记录失败原因，并明确返回数据状态，不伪造成功。
- 如何避免未来函数：当日信号只使用当日及以前数据，策略收益从下一交易日开始计算。
- 为什么 Pages 不能完成全栈部署：Pages 只托管静态文件，不能运行 Python 进程、SQLite 写入或定时任务。
- 为什么暂不做实盘：实盘还需要账户权限、审计、限额、熔断、人工确认和更高等级的可靠性保障。
