# 前端接口契约草案

本文档用于前端、后端和算法模块合并前对齐数据边界。路径默认以 `VITE_API_BASE_URL=/api` 为前缀。

## 通用约定

- 请求和响应均使用 `application/json; charset=utf-8`。
- 日期使用 `YYYY-MM-DD`，时间戳使用 ISO 8601。
- 百分比字段使用数字表达，例如 `12.5` 表示 `12.5%`。
- 金额和指数点位使用数字，前端负责格式化展示。
- 所有接口建议返回稳定字段名，避免直接返回模型内部字段。

错误响应统一格式：

```json
{
  "code": "INVALID_ARGUMENT",
  "message": "assets 至少需要 2 个有效资产代码",
  "details": {},
  "traceId": "req_20260708_001"
}
```

## GET /health

用于部署和联调时确认服务可用。

响应：

```json
{
  "status": "ok",
  "version": "0.1.0",
  "time": "2026-07-08T10:00:00+08:00"
}
```

## GET /market/overview

返回市场概况、指数表现和行业资金热度。

响应：

```json
{
  "snapshotTime": "2026-07-08T15:00:00+08:00",
  "sentiment": {
    "label": "中性偏强",
    "score": 58,
    "advancers": 2156,
    "decliners": 1844
  },
  "indexes": [
    { "name": "上证指数", "value": 3258.63, "changePct": 0.85 },
    { "name": "深证成指", "value": 10897.32, "changePct": 1.23 }
  ],
  "sectorFlows": [
    { "sector": "科技", "netInflow": 78, "netOutflow": -26 },
    { "sector": "金融", "netInflow": 40, "netOutflow": -18 }
  ]
}
```

## POST /analytics/correlation

根据资产池返回相关性矩阵。

请求：

```json
{
  "assets": ["AAPL", "MSFT", "GOOGL", "AMZN"],
  "windowDays": 120
}
```

响应：

```json
{
  "assets": ["AAPL", "MSFT", "GOOGL", "AMZN"],
  "matrix": [
    [1, 0.82, 0.73, 0.68],
    [0.82, 1, 0.75, 0.7],
    [0.73, 0.75, 1, 0.66],
    [0.68, 0.7, 0.66, 1]
  ],
  "windowDays": 120,
  "generatedAt": "2026-07-08T15:00:00+08:00"
}
```

## POST /backtests

运行策略回测并返回指标、收益曲线和回撤曲线。

请求：

```json
{
  "assets": ["AAPL", "MSFT"],
  "strategy": "ma_crossover",
  "startDate": "2025-01-01",
  "endDate": "2025-12-31",
  "params": {}
}
```

响应：

```json
{
  "strategy": "ma_crossover",
  "assets": ["AAPL", "MSFT"],
  "summary": "均线交叉 · 2025-01-01 至 2025-12-31",
  "metrics": {
    "sharpeRatio": 1.25,
    "alpha": 0.08,
    "beta": 0.92,
    "maxDrawdownPct": -12.5,
    "totalReturnPct": 24.8
  },
  "returnSeries": [
    { "date": "2025-01-31", "returnPct": 2.5 }
  ],
  "drawdownSeries": [
    { "date": "2025-01-31", "drawdownPct": -2.1 }
  ]
}
```

## GET /strategies/ranking

返回策略排行榜。

响应：

```json
{
  "items": [
    {
      "name": "强化学习策略",
      "todayReturnPct": 2.5,
      "weekReturnPct": 8.2,
      "monthReturnPct": 15.6,
      "annualReturnPct": 32.4,
      "sharpeRatio": 1.8
    }
  ]
}
```

## POST /allocation/suggestion

根据资产池和可选风险偏好生成配置建议。

请求：

```json
{
  "assets": ["AAPL", "MSFT", "GOOGL", "AMZN"],
  "riskPreference": "balanced"
}
```

响应：

```json
{
  "totalWeight": 100,
  "items": [
    {
      "asset": "AAPL",
      "weight": 30,
      "yesterdayPerformancePct": 1.2,
      "trend": "上涨"
    }
  ],
  "generatedAt": "2026-07-08T15:00:00+08:00"
}
```

## 枚举建议

策略 `strategy`：

- `ma_crossover`
- `momentum_reversal`
- `reinforcement_learning`
- `multi_agent`

风险偏好 `riskPreference`：

- `conservative`
- `balanced`
- `aggressive`
