# 算法与数据模块

本目录由数据/算法组接手，技术栈固定为 Python 3.11+、AkShare、Pandas。
HTTP 唯一契约是 `packages/contracts/openapi.yaml`，Python 基础类型和协议位于：

- `src/quant_platform/models.py`
- `src/quant_platform/interfaces.py`

## 实现顺序

1. `AkShareMarketDataProvider`：30–50 个 A 股/ETF、日线、更新状态、市场概况；
2. `ma_cross` 与 `momentum_reversal` 两个传统策略；
3. 2–10 个资产的 Pandas 相关矩阵；
4. 含交易成本的异步回测、净值、交易记录和六项指标；
5. 真实结果驱动的日更排行和下一交易日模拟配置。

要求：

- 代码始终是六位字符串，列名统一为
  `date/open/high/low/close/volume/amount`；
- 收盘生成信号、下一交易日开盘成交，禁止未来函数；
- DQN、PPO、多智能体完成前标记 planned，不进入排行；
- 不在算法包导入 Flask，不返回随机成绩；
- 覆盖空数据、停牌、重复日期、无交易、全亏损和数据源超时。

```bash
python -m pip install -e "services/algorithms[dev]"
ruff check services/algorithms
pytest services/algorithms
```

完整分工与验收标准见 `docs/implementation-guide.md`。

## 行情缓存与服务器日更契约

后端不得在每个 HTTP 请求中直接调用 AkShare。统一使用
`AkShareMarketDataProvider`：历史行情和市场概览均优先读取
`data/processed/` 中的本地缓存，只有缓存缺失时才尝试真实数据源。

- A 股和 ETF 日线通过 `stock_zh_a_hist_tx` 使用腾讯数据源；该接口返回的
  `amount` 实际表示成交量（手），适配层会将其映射为统一契约的 `volume`，
  无法获得的成交额 `amount` 保持为空，禁止用 0 伪造。
- 上游失败但存在旧缓存时继续返回旧数据，`update_daily()` 状态为 `stale`；
  没有任何可用缓存时状态为 `failed`。后端应将无缓存的
  `UpstreamUnavailableError` 映射为统一的 `503 UPSTREAM_UNAVAILABLE`。
- 市场概览仍需使用东方财富全市场快照，但只允许日更任务调用一次；普通请求
  读取 `market_overview.json`。不得在 Flask 路由中循环调用 AkShare。
- OHLCV 和日更状态存放在 `market_data.db`，SQLite 使用 WAL 和短生命周期连接，
  支持 CLI 与 Flask 跨进程读取同一份缓存；市场概况仍通过临时文件原子替换写入
  `market_overview.json`。`data/processed/` 是服务器运行数据目录，已被 Git 忽略；
  部署时必须放在持久化磁盘，并保证同一时刻只有一个日更任务。

安装算法包后，服务器在每个交易日收盘后执行：

```bash
quant-data-update
# 或
python -m quant_platform.cli
```

CLI 会输出 JSON 状态，退出码 `0` 表示 `ready`、`2` 表示有缓存可用但数据
`stale`、`1` 表示 `failed`。Linux 服务器可配置 cron（项目路径按实际部署修改）：

```cron
20 16 * * 1-5 cd /srv/intelligent-quant-analysis-platform && .venv/bin/quant-data-update >> /var/log/quant-data-update.log 2>&1
```

首次部署应先手动运行一次并确认生成 `market_data.db` 和
`market_overview.json`，再启动后端。定时任务与 Flask 进程共享同一个
`data/processed/` 目录；SQLite 数据库文件必须放在持久化磁盘，且保持现有
Python 接口与 OpenAPI 响应结构不变。
