# 算法与数据模块

`services/algorithms` 提供行情缓存、传统策略、回测、策略排行和资产配置能力，供 Flask 后端统一调用。模块不直接面向浏览器，也不负责真实交易。

## 已实现能力

- 约 30–50 个 A 股和 ETF 的默认资产池。
- AkShare 主数据源与 Tencent 行情适配。
- SQLite 行情缓存、旧 CSV 数据导入和缓存状态管理。
- 交易日识别、增量更新和市场概览快照。
- Pearson 相关性分析。
- 均线交叉与动量反转策略。
- 避免未来函数的回测、收益/波动/回撤/胜率等指标。
- 统一评估区间下的策略排行。
- 基于风险预算与约束的次日模拟配置。

DQN、PPO 和多智能体策略只保留为策略目录中的 `planned` 项，不应在演示或答辩中表述为已实现。

## 安装与测试

在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/algorithms[dev]"
ruff check services/algorithms
pytest services/algorithms
```

测试默认使用固定样本或模拟数据源，不访问真实网络。真实 AkShare/Tencent 连通性应在独立环境检查，避免把第三方波动误判为算法回归。

## 初始化与每日更新

```bash
quant-data-update
# 或 python -m quant_platform.cli
```

默认数据目录为仓库根目录下的 `data/processed/`：

- `market_data.db`：资产、日线、更新运行记录和元数据。
- `market_overview.json`：市场概览快照。
- `*.csv`：历史版本生成的缓存，可在首次启动时迁移到 SQLite。

增量更新会从每个资产最后成功日期附近开始补齐数据，并保留最后一次成功缓存。建议在交易日收盘后通过 cron 或 systemd timer 调用更新命令；调度器不内置在算法包中。

## 运行约束

- 数据状态分为 `ready`、`updating`、`stale` 和 `failed`。
- 数据源失败时优先读取最后一次成功缓存，并把过期或失败原因暴露给后端。
- 策略信号使用当日收盘后可获得的数据，收益从下一交易日开始计算，避免同日信号偷看未来。
- 策略排行在同一资产池、区间和成本假设下比较，并保留足够预热窗口。
- 配置结果是研究用途的模拟建议，不连接券商、不提交订单，也不替代独立风控和人工确认。

## 维护要求

算法或字段变化必须同步更新：

1. 算法单元测试和回归测试；
2. `packages/contracts/openapi.yaml`（若接口结构变化）；
3. 后端适配与接口测试；
4. 相关文档和答辩口径。

数据源字段可能随上游调整，解析逻辑应继续使用显式列映射、类型校验和可追踪错误，不能静默吞掉异常。
