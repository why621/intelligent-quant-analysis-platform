# Algorithm interfaces

本目录只定义算法组的输入、输出和扩展边界，不提前替组员实现策略。

固定技术栈：

- Python 3.11+
- AkShare：行情与公开金融数据适配
- Pandas：清洗、对齐、因子和回测表格计算

组员首先实现：

1. quant_platform.data.AkShareMarketDataProvider
2. quant_platform.backtesting.BacktestEngine
3. 对应单元测试和固定的小型测试数据

安装与检查：

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e "services/algorithms[dev]"
    ruff check services/algorithms
    pytest services/algorithms

接口实现必须输出稳定英文列名，不得把 AkShare 的中文原始列名直接暴露给后端或前端。
回测必须明确手续费、滑点、复权方式、时间区间和未来数据泄漏防护。
