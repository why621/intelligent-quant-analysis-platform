## CR070 / OpenAPI 0.14.0（2026-10-20，生产接入与发布验收中）

用户已授权正式候选训练、生产接入及发布。新增`portfolio_masked_sac`实验组合策略，复用共享账户回测、POST当前配置排行榜及模拟配置接口，参数仍为明确的`modelRef`。服务目录允许四个互不重复的组合模型，保留CR069三模型及旧四单资产模型。

`modelContext.representationLearning`可选字段披露architecture、method、poolChanges和performanceImprovement：当前为掩码特征重建/共享注意力、训练内换池、收益改进未证明。网页请求仍是固定的用户所选2–10资产，不接受未经定义的池切换时间表。换池Python返回信息不是HTTP接口。

新权重必须走独立架构白名单、安全Tensor加载、正式训练至少65536步、bundle/evaluation哈希匹配、全目录跨资产执行证据的原有发布门禁。小试训研究包仍拒绝注册生产；新模型未通过发布验收前不视为已上线。接口声明与生产实际发布状态以部署记录为准。

本地机制完成记录见[实用交付](cr070-practical-delivery-2026-10-20.md)，后续发布见[CR070部署记录](cr070-deployment-2026-10-20.md)。

## CR069 / OpenAPI 0.13.0（2026-10-15，云端已部署）

- 新增POST /api/strategies/ranking，复用BacktestRequest。资产、起止、策略参数、资金、成本、复权、现金、组合模式与基准均参与计算与配置快照。当前策略使用用户参数，其他候选使用明确的目录默认参数；不把不同策略的参数名称强行复用。
- ResearchRankingResponse返回request/configHash/dataContext/asOfDate、实际评价起止及观察点、资产和费用；每行含parameters/metrics/costSummary/benchmarkContext等适用字段。所有参与行必须覆盖同一完整交易日历，不截短日期、不换成510300、不覆盖用户费用；当前策略不可计算时请求报错，其他候选排除并在unavailableStrategies解释。
- 排行区间最多366天、至少两个交易日，按区间收益降序排列。传统策略可用单资产，联合模型需要2–10只。计算复用回测校验与引擎，不创建持久化回测任务。
- 缓存绑定完整请求、候选参数及模型、行情版本，每进程最多128份。30秒协作预算、每进程2个并行计算上限与同请求合并；预算不能强行中断任意底层CPU计算。前端等待45秒、不自动重试，手动刷新可能复用匹配缓存，临时失败不缓存。
- 前端主动提交计算，配置变化立即标旧且禁载入，校验版本并丢弃迟到响应。GET旧代表资产排行保留兼容；POST不沿用GET的period/historyStartDate语义，前端不再启动固定510300榜。
- 新组合发布范围assetScope=published_universe绑定完整327资产目录/类型、目录版本、冻结数据版本与独立跨资产证据；支持当前目录任意2–10只股票/ETF、请求成本和额外现金预留。训练成本与执行成本分别披露。缺少匹配证据拒绝加载；旧CR066 bundle仍按训练池、固定费用及零额外现金限制。
- 每只资产仍须足够真实预热，研究起点在训练/验证之后；已确认停牌仅延续最近真实特征和估值并禁止成交，未知缺口与上市前无价格拒绝，历史不足以422 RL_INSUFFICIENT_HISTORY给出原因。基准首日停牌可在已核实连续停牌范围追溯此前真实收盘，不生成OHLCV。
- 本节接口已部署云端；正式服务与日更镜像独立，发布证据见[CR069部署](cr069-deployment-2026-10-15.md)。模型保持experimental，执行覆盖不代表全部组合穷举或长期超额收益。详见[CR069验收](cr069-universe-ranking-2026-10-15.md)。以下旧版本段落保留对应历史语义。

## CR066 / OpenAPI 0.12.0（2026-10-12，开发）
新增独立portfolio_ppo/sac/td3目录，modelContext.portfolioMode=joint_portfolio、minAssets/maxAssets与冻结evaluation；allocationEnabled显式开放实验模拟。请求仍使用shared_account，同一训练池内2–10资产，成本按manifest，现金由模型输出，额外cashPct=0。服务读取请求起点之前历史预热，曲线从请求样本外起点开始；联合模型暂不支持共同交易日缺口，不静默填充或跨日补单。旧四模型及固定510300排行不变。新QUANT_PORTFOLIO_RELEASE独立白名单，验证正式候选/评估/权重哈希，拒绝smoke权重。

# 统一 API 契约

## CR065 / OpenAPI 0.11.0（2026-10-11，本地开发）

- `BacktestRequest`增加`portfolioMode=shared_account|legacy_independent`、`benchmarkMode=buy_and_hold|custom|none`与`cashPct`。新页面显式选择共享账户和买入持有；旧请求缺省保持原独立分账及基准省略语义，旧任务JSON不改写。旧510300模型只能使用`legacy_independent`且不支持额外现金预留。
- `TradingCosts.stampDutyMode=fixed|asset_date`：缺省fixed兼容旧实验；asset_date按实际成交日及资产目录类型处理，ETF印花税为0、股票仅卖出按历史税率。费率字段可以分别省略并使用契约缺省值，拒绝非有限值及100%以上费率。
- 结果可选`accountCurve`记录收盘现金、净值、逐资产实际仓位和累计费用；`costSummary`分列交易数、佣金、印花税、显性费用、滑点及合计。Trade附三项成本。`feeCny`继续只表示佣金和印花税，滑点已经包含在成交价格中，不再次扣现金。旧任务缺失诊断字段时表示未记录，不等于0。
- `benchmarkEquity`继续是归一化价格序列，策略`equity`是人民币账户净值。`buy_and_hold`表示请求窗口首个实际收盘初始等权持有，后续不再平衡、不计费；`benchmarkContext`披露模式、实际首末日、标的、口径及名称。不得将该参考曲线称为扣费后可执行账户收益。
- 排行保留510300研究口径，增加`evaluationStartDate/evaluationEndDate/historyStartDate/observationCount/tradingCosts`及每行`parameters`。日期来自实际净值切片；1d取最后两条记录。策略在评价窗口之前已运行，评价起点可带持仓；将该窗口导入从全现金启动的回测不保证收益数值相同。
- 模拟请求增加`parameters/adjust/tradingCosts/initialCapitalCny/startDate`，响应`request`记录实际配置。使用同一共享组合引擎从该起点全现金重放至依据日，再形成下一交易日目标；中性信号不会凭空开仓。最新交易日及数据缺口门禁保留，未来成交价/实际费用尚未知。allocation预检支持同一`startDate`，省略时使用365自然日回看。
- 本节登记本地契约变化，不代表云端和Pages已升级。正式训练与发布另行确认。
- 共享账户的`executeAt=next_open`表示下一统一交易日开盘，只对当日有真实行情的资产成交。已核实停牌仅沿用最近收盘估值、冻结持仓；未成交目标不自动挂到复牌日，`nonTradingExecution=skip_untradable_no_pending_order`明确这一限制。首日必须具备所有标的真实估值，未知缺口仍拒绝；不合成OHLCV。
- 共享估值轴从实际首日到请求截止日使用官方交易日历，即使全部所选资产同日或尾段停牌，也保留账户估值并当日失效未成交信号；全资产缺日而无核实事件时拒绝，非官方交易日行情同样拒绝。不能以行情日期并集跨过该日并在复牌日补成交，也不能裁掉共同停牌尾段。

> 契约声明：`packages/contracts/openapi.yaml` 是前端、Flask 后端和 Python
> 算法模块之间唯一具有约束力的 HTTP 契约。本文件用于解释契约，示例与
> OpenAPI 冲突时，以 OpenAPI 为准。任何字段、路径或枚举变更都必须在同一个
> Pull Request 中先修改契约，再修改实现和测试。

## 1. 项目边界

- 数据范围：当前固定目录300只股票和27只场内ETF，共327只；具体可用性以发布包状态为准。
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
  "startDate": "2025-01-01",
  "endDate": "2025-12-31",
  "benchmark": "510300",
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


## CR-009 M0（2026-09-08）

默认无基准，示例510300明确为ETF而非独立指数。回测查询新增request原始快照；已有任务不重算。参数Schema的default须由客户端提交，x-relations表达字段lt关系，服务端仍校验必填和业务关系。相关性/回测在入队或计算前按已发布截止及2025—2026日历校验，越界400 DATE_OUT_OF_RANGE，无截止或历史failed返回503 DATA_NOT_READY；范围内真正源失败保留503 UPSTREAM_UNAVAILABLE。全局截止不保证每只资产完整，原有逐资产完整性检查保留。
# CR-011增量 / API契约0.4.0（2026-09-08）

资产目录新增offset分页、matchedTotal、nextOffset、catalogVersion和只读assetId；total继续表示本页数量。稳定排序为(exchange, symbol, assetType)，过滤先于分页。前端须完整读取同版本分页，混版或中途失败不发布部分目录；旧接口无分页元数据时提示升级后重试，不把一页当完整目录。目录版本不是行情覆盖或官方成分版本。默认池本批仍为旧50只；完整300只是真实名单及行情的后续验收目标。独立指数接口尚未实现，研究请求仍用六位股票/ETF代码。详见 [M1设计](m1-catalog-design.md)。
## CR-012磁盘快照契约（非HTTP接口）

新增packages/contracts/schemas/universe.yaml#/UniverseSnapshot，schemaVersion=1；当前官方名单300股票及源文件哈希/日期/来源绑定，effectiveDate为null、historicalMembershipVerified=false。API仍0.4.0，没有新增快照路由，也未把index:CSI:000300作为当前股票/ETF研究请求。显式provider注入仅在隔离验证启用，默认运行资产池未切换。详见 [CR-012报告](cr012-universe-validation-2026-09-08.md)。


## CR-037：逐资产部分发布（0.8.0，2026-09-15）

不可变发布schemaVersion=2保留全部327资产目录，每只资产可含经校验的部分真实行情或上个已发布版本的整段历史。API的latestTradeDate/dataContext.publicationDate是批次目标日，不能推断327资产均已有当日成交；data/status新增availability，包含readyCount、affectedCount、indexState/indexTradeDate及逐symbol的state、lastTradeDate、suspended、missingSessions。旧v1读取仍要求完整，HTTP新增字段可选以兼容旧服务。

历史查询只接受所选资产在所选区间内完整覆盖或已核实非交易事件；未知缺口返回503，不静默删除资产，不补造OHLCV。MarketOverview新增unavailable与partial；priced+已知非交易suspended+unavailable=300，未知缺失不计为平盘；同日指数不可用时indices为空。策略排行明确evaluationSymbols=[510300]；该依赖缺数据时排行不可用，其他股票分析不受其阻断。日更partial不计入连续两实际交易日完整自动验收；新读端与执行器须配套升级，旧云镜像不能读取v2。


## CR039 / OpenAPI 0.9.0（2026-09-15，本地实现）

新增POST /api/data/capability：按module=overview/correlation/backtest/ranking/allocation预检当前不可变批次。相关性/回测提供symbols、startDate/endDate，回测可附benchmark；配置提供symbols；排行period默认30d，实际依赖510300及90日预热。返回state=ready/partial/unavailable/unknown、dataContext、实际所需起止日和issues（具体symbol/code/message）。沿用X-Research-Version，冲突409；格式错误400。ready只保证数据覆盖，不代替计算时的参数和数值有效性检查；旧提供者返回unknown，不触发采集。

/data/status.availability及/data/coverage.items[].availability增加tradingState和可选update。update含outcome=updated/partial/retained、标准失败reason、retryable、attempted、真实lastTradeDate。retryable不授予额外采集预算。availability.eventMaintenance记录核验日/目标日、源状态、原响应SHA256及冲突；SSE股票源已验证，SZSE/ETF仍pending，不能把它解释为全市场停复牌覆盖。响应Schema以packages/contracts/schemas/data.yaml为准，前端五模块预检与资产提示同步；预检断网/旧接口缺失给可重试提示，实际提交仍保留原校验。


## CR065 云部署状态（2026-10-11）

OpenAPI 0.11.0 配套实现和云前端已上线，候选及实际 HTTPS 验收通过；旧请求缺省、旧任务 JSON 和四个单资产模型保持兼容。GitHub Pages 尚待 PR #47 合并及独立验收。联合组合研究模型尚未接入网页接口。详见 [部署报告](cr065-deployment-2026-10-11.md)。

### CR065 GitHub Pages 正式验收完成（2026-10-11）
用户确认合并 PR #47，main 提交 ebe760bb2d2991607b458a67a689a062cab395de；Pages 工作流 38122591031 success。实际 https://why621.github.io/intelligent-quant-analysis-platform/ 入口 index-BR1Ms9tA.js，Edge 1440/390 真实浏览器 33 项通过、21 个业务请求全部成功，无 pageerror、console error、requestfailed 或横向溢出，手机截图已查看。
验证资产联动/手动覆盖恢复、默认基准和共享账户、费用账本、模拟八项配置一致、排行六策略及实际日期、排行载入、旧 TD3 结果恢复。新增一次真实验收任务 8b706e73-faec-4a2c-93f9-05490f91d5e7，保留记录；不改写旧任务。未重复云部署、训练或行情采集，07:30 日更配置未改。联合 RL 正式模型和网页集成仍未完成，不将网站发布等同正式组合模型发布。
证据在原仓库 ignored artifacts/cr065-deploy/pages-browser.json、pages-backtest.json、pages-allocation.json、pages-ranking.json 和 pages-backtest-1440/390.png。复现命令：node artifacts/cr065-deploy/online_browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/ 。验收文档推送 codex/cr065-pages-evidence；该文档分支合并与否不影响已完成的 Pages 发布。

CR066云端实现已部署并通过13隔离任务及19公网浏览器检查；Pages待PR48合并验收。详细边界见2026-10-12验收记录。

### CR066 Pages 正式验收完成（2026-10-12）
PR #48合并提交7aa9e9836778bbd871b18ac0f6b62eafa8ea79c7，Pages工作流38230719515 success。实际 https://why621.github.io/intelligent-quant-analysis-platform/ 入口index-BmC4Uxgy.js；19项真实Edge检查、18个跨域业务请求全部成功，无运行错误，1440/390/320无横向溢出。十资产PPO联合回测及同配置模拟成功，模型范围/评估披露、资金权重和、七项配置深比较通过。
新增Pages验收任务e7989118-efe5-4e62-bebb-2d3f66290f9c，独立记录；云与Pages合计本轮新增两个真实验收任务，原139条未改写。云端与Pages均完成，不再等待功能合并。未重复训练/云切换，旧模型/日更配置保持。证据ignored artifacts/cr066-training/pages-browser.json、pages-job.json、pages-1440/390/320.png，命令node artifacts/cr066-training/browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/。
最终SDD/README/部署及交接记录推送codex/cr066-pages-evidence；该文档分支是否合并不影响已上线功能。剩余研究限制：首批训练池内2–10资产，短历史与非全新盲测，未知资产泛化及长期超额收益未证明；停牌缺口暂不支持。扩大池、长期样本和重新训练另行登记。
