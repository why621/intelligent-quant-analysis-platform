# 后端与算法接手指南

开始前必须阅读 [`api-contract.md`](api-contract.md) 和
[`openapi.yaml`](../packages/contracts/openapi.yaml)。不得自行改字段。

## 分工

| 负责人 | 目录 | 交付物 |
| --- | --- | --- |
| 数据/算法 | `services/algorithms` | AkShare 日线、清洗、相关性、策略、回测、排行、配置 |
| 后端 | `services/backend` | Flask 路由、校验、异步任务、存储、错误映射 |
| 前端 | `apps/frontend` | 只通过 `src/services/api.js` 调用接口并删除对应 mock |

每人从最新 `main` 建 `feat/<module>-<name>` 分支，通过 PR 合并。

## 1. 数据组

1. 维护 30–50 个 A 股/ETF；代码始终是六位字符串。
2. 使用 AkShare 获取日线，统一为
   `date/open/high/low/close/volume/amount`，日期升序并去重。
3. 保留原始与清洗后数据；初期 CSV，随后迁移 SQLite。
4. 交易日收盘后增量更新，记录 status、latest_trade_date、updated_at、message。
5. 网络失败保留旧数据，`/data/status` 返回 stale/failed，不能假成功。

验收：价格和成交量非负、同资产同日期唯一、无未来日期，停牌和非交易日可解释。

## 2. 算法组

先实现：

- `ma_cross`：短均线上穿/下穿长均线；
- `momentum_reversal`：在策略目录中声明参数与信号规则；
- 相关性：2–10 个资产按共同日期对齐收益率后使用 Pandas `corr()`；
- 回测：收盘出信号、下一开盘成交，扣佣金、印花税和滑点；
- 指标：总收益、年化收益、最大回撤、Sharpe、Alpha、Beta；
- 日更排行与下一交易日模拟权重。

接口位于 `services/algorithms/src/quant_platform/models.py` 和 `interfaces.py`。
DQN、PPO、多智能体完成前必须标记 planned，不得进入真实排行。

测试至少覆盖：空数据、停牌、重复日期、短窗口大于长窗口、无交易、全亏损、
无基准、AkShare 超时和任务失败。任何策略都不得读取未来行。

## 3. 后端组

路由只负责解析、校验、调用服务和序列化，不在路由内编写 Pandas 计算。按顺序替换
当前 `501 NOT_IMPLEMENTED`：

1. `/health`、`/data/status`；
2. `/assets`、`/assets/{symbol}/history`；
3. `/strategies`、`/analytics/correlation`；
4. `/backtests`、`/backtests/{jobId}`；
5. `/strategies/ranking`、`/allocation/suggestion`。

回测使用异步任务；状态仅按
`queued → running → succeeded|failed` 转换。未实现时返回明确 501，禁止随机数据。

## 4. 前端联调

每个模块都验证 loading、empty、error、success 四种状态。只有接口返回成功才展示
真实指标；接口未完成时保留“待接入”提示。每替换一个接口就删除对应演示占位。

## 5. 云服务器与日更

GitHub 不直接提供运行中的 API。正确链路：

1. PR 合并 `main`；
2. GitHub Actions 运行契约、Python 测试和前端构建；
3. CI 成功后 SSH 部署指定 commit 到服务器并重启服务；
4. systemd/容器运行 Flask，Nginx 代理 `/api`；
5. cron/systemd timer 在收盘后运行更新、回测与排行；
6. 成功后原子切换新数据；失败保留旧数据并告警；
7. 检查 `/api/health`、`/api/data/status` 和冒烟请求。

服务器 IP、SSH 私钥、数据库密码只放 GitHub Secrets 或服务器环境变量。

## 每个 PR 的完成定义

- 契约、Flask、算法 DTO 和前端字段一致；
- Ruff、pytest、前端构建通过；
- 有正常、边界和错误测试；
- 无 Token、私钥、服务器 `.env` 或大体积行情文件；
- 无未来函数，单位与契约一致；
- PR 写明改动、测试、限制与回滚方式。
