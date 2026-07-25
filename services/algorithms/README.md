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
