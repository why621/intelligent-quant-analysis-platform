# 统一 API 契约

> 契约声明：`packages/contracts/openapi.yaml` 是前端、Flask 后端和 Python
> 算法模块之间唯一具有约束力的 HTTP 契约。本文件用于解释契约，示例与
> OpenAPI 冲突时，以 OpenAPI 为准。任何字段、路径或枚举变更都必须在同一个
> Pull Request 中先修改契约，再修改实现和测试。

## 1. 项目边界

- 数据范围：A 股和场内 ETF，初期维护 30–50 个资产。
- 数据来源：AkShare；历史行情使用日线 OHLCV，默认前复权。
- 更新频率：交易日收盘后日更，不承诺盘中实时行情。
- 配置建议：使用最近一个交易日收盘数据生成下一交易日模拟权重。
- 研究用途：不连接券商、不保存交易密码、不提交真实订单。
- 技术边界：Flask 负责 HTTP、校验和任务状态；Pandas/算法包负责计算；
  前端只消费 JSON，不直接调用 AkShare。

## 2. 通用规则

| 项目 | 统一约定 |
| --- | --- |
| 根路径 | `/api` |
| HTTP 字段 | `camelCase` |
| Python 名称 | `snake_case`，在 HTTP 边界显式转换 |
| 日期 | `YYYY-MM-DD` |
| 时间 | ISO 8601，服务器业务时区 `Asia/Shanghai` |
| 资产代码 | 六位数字字符串，如 `510300`，不能转成整数 |
| 金额 | 字段名以 `Cny` 结尾，单位为元 |
| 百分比 | 字段名以 `Pct` 结尾，使用百分点；`8.5` 表示 `8.5%` |
| 空值 | 数据确实不可得时返回 `null`，不使用 `0` 或空字符串冒充 |
| JSON | `application/json; charset=utf-8` |

错误响应统一为：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "symbols 必须包含 2 到 10 个不同资产代码",
    "details": {
      "field": "symbols"
    }
  }
}
```

建议使用的错误码：

- `VALIDATION_ERROR`：字段缺失、格式错误或日期范围非法；
- `ASSET_NOT_FOUND`：资产不在资产池；
- `STRATEGY_NOT_AVAILABLE`：策略未完成或不可执行；
- `DATA_NOT_READY`：数据尚未更新完成；
- `JOB_NOT_FOUND`：回测任务不存在；
- `UPSTREAM_UNAVAILABLE`：AkShare 或外部数据源暂时不可用；
- `INSUFFICIENT_DATA`：请求合法但数据不足以计算（422）；
- `INTERNAL_ERROR`：未预期的服务端错误。

## 3. 接口总表

| 方法与路径 | 用途 | 后端完成标准 |
| --- | --- | --- |
| `GET /health` | 服务存活检查 | 不访问数据库和 AkShare |
| `GET /data/status` | 日更任务状态与最新交易日 | 能区分 ready/updating/stale/failed |
| `GET /assets` | 查询资产池 | 支持代码/名称及 stock/etf 筛选 |
| `GET /assets/{symbol}/history` | 获取复权日线 | 日期升序，不重复，不含未来数据 |
| `GET /market/overview` | 市场宽度、指数与资金热度 | 结果带实际交易日。 |
| `POST /analytics/correlation` | 2–10 个资产收益率相关矩阵 | 矩阵对称、对角线为 1 |
| `GET /strategies` | 策略目录和参数说明 | 清楚标记 available/experimental/planned |
| `GET /strategies/ranking` | 日更策略排行 | 只展示真实跑出的结果 |
| `POST /backtests` | 提交异步回测 | 返回 HTTP 202 和 jobId |
| `GET /backtests/{jobId}` | 轮询任务与获取结果 | succeeded 时 result 非空 |
| `POST /allocation/suggestion` | 下一交易日模拟配置 | 权重加现金为 100，带免责声明 |

完整字段、必填项和枚举见
[`packages/contracts/openapi.yaml`](../packages/contracts/openapi.yaml)。

## 4. 关键调用示例

### 4.1 资产相关性

```http
POST /api/analytics/correlation
Content-Type: application/json
```

```json
{
  "symbols": ["510300", "510500", "159915"],
  "startDate": "2025-01-01",
  "endDate": "2025-12-31",
  "adjust": "qfq",
  "returnType": "simple"
}
```

响应中 `symbols` 的顺序决定 `matrix` 的行列顺序。先按日期做内连接，再对
收益率序列计算相关系数，并返回实际 `observationCount`。

### 4.2 异步回测

```http
POST /api/backtests
Content-Type: application/json
```

```json
{
  "symbols": ["510300"],
  "strategyId": "ma_cross",
  "parameters": {
    "shortWindow": 5,
    "longWindow": 20
  },
  "startDate": "2024-01-01",
  "endDate": "2025-12-31",
  "benchmark": "000300",
  "initialCapitalCny": 100000,
  "adjust": "qfq",
  "tradingCosts": {
    "commissionPct": 0.03,
    "stampDutyPct": 0.05,
    "slippagePct": 0.02
  }
}
```

受理响应：

```json
{
  "jobId": "8f316d85-e86b-45c5-8ff6-c8ee2457e71b",
  "status": "queued",
  "createdAt": "2026-07-25T16:20:00+08:00",
  "updatedAt": null,
  "progressPct": 0,
  "result": null,
  "error": null
}
```

前端随后每 1–2 秒调用
`GET /api/backtests/8f316d85-e86b-45c5-8ff6-c8ee2457e71b`。状态只能按
`queued → running → succeeded|failed` 转换；失败时填写 `error`，成功时填写
`result`。当前实现使用 SQLite 持久化任务，并由后台 worker 原子领取 `queued` 任务；服务重启后仍可继续处理排队任务。

回测统一假设：

- 使用当日收盘价生成信号，下一交易日开盘价成交，避免未来函数；
- 中国交易日历、人民币计价；
- 佣金、印花税和滑点必须进入计算；
- `maxDrawdownPct` 使用非负绝对值；
- 无基准时 `alphaPct`、`beta` 返回 `null`。

### 4.3 下一交易日模拟配置

```json
{
  "symbols": ["510300", "510500"],
  "strategyId": "momentum_reversal",
  "cashPct": 10
}
```

响应必须同时给出 `basisDate` 和 `targetDate`，且：

```json
{
  "basisDate": "2026-07-24",
  "targetDate": "2026-07-27",
  "strategyId": "momentum_reversal",
  "positions": [
    {
      "symbol": "510300",
      "weightPct": 55,
      "action": "increase",
      "reason": "示例：动量信号为正"
    },
    {
      "symbol": "510500",
      "weightPct": 35,
      "action": "hold",
      "reason": "示例：信号中性"
    }
  ],
  "cashPct": 10,
  "advisoryOnly": true,
  "disclaimer": "仅用于教学研究，不构成投资建议，不会提交真实订单。"
}
```

## 5. 契约变更流程

1. 从 `main` 拉取最新代码，建立 `feat/<module>-<short-name>` 分支。
2. 先修改 OpenAPI 和本说明，再补 Flask、算法、前端与测试。
3. 新增可选字段属于向后兼容变更；删除、改名、改变含义都属于破坏性变更。
4. 破坏性变更必须说明迁移方式，并由前端、后端、算法负责人共同审核。
5. PR 合并前至少验证：契约能解析、后端测试通过、前端构建通过。

禁止在未改契约的情况下让前端“猜字段”，也禁止用固定随机数伪装真实策略结果。
