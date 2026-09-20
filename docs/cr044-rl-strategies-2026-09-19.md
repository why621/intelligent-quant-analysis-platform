# CR-044 单智能体强化学习策略接入（算法模块）

> 2026-09-20 当前实现已由 [CR-045 修复与验证](cr045-rl-review-fixes-2026-09-20.md) 更新：推理使用引擎实际持仓回调，训练/回测共用执行内核，manifest v2 绑定元数据及权重，旧模型需重训，短区间返回样本不足。以下保留 CR044 历史记录；“离散分支逐字节不变”仅描述当时实现，CR045 保留其行为并抽取内核；旧收益与验证数字不代表修复后的重新评估。


日期：2026-09-19 ｜ 负责：算法模块 ｜ 状态：算法侧代码完成，`experimental` 起步，未过评估阶梯不转 `available`

## 1. 动机与范围

学长建议集成单智能体 RL 方法（参考 FinRL 2021）。经确认本轮范围：**DQN / PPO / SAC / DDPG 四种**，目标"完整运行时可回测"，用 **stable-baselines3 薄封装**；毕业论文算法、多智能体、实盘、后端注册与前端页面均**不在本轮**。

工作严格限定在 `services/algorithms/**`。后端（`services/backend/**`）与前端（`apps/frontend/**`）由其他同学负责，本文只给出**接口约定与交接清单**。

## 2. 算法侧已交付

### Step A — 引擎支持连续动作（T-023，完成）
- `models.py`：`StrategyInfo` 追加尾部默认字段 `signal_semantics`（`discrete_hold` | `continuous_target_weight`）与 `requires_trained_model`，既有构造调用零改动。
- `backtesting/engine.py`：
  - `_resolve_strategy()`：策略若暴露 `create_for_request(parameters)`（鸭子类型，同 `nontrading_sessions`/`cache_revision` 约定）则返回 **per-request 新实例**，否则沿用共享单例 → RL 权重不进共享实例、无并发竞争。
  - `_simulate()` 增 `continuous_target_weight` 分支：`w=clip(signal,0,1)`，决策日收盘权益×w 为目标市值，次日开盘 `open·(1±slippage)` 成交，`|Δ|<max(band_pct·equity, min_trade_cny)` 跳过再平衡；预热 NaN 走 `ffill().fillna(0)`（沿用上一目标，**不**强制清仓）。**离散分支逐字节不变。**
  - `assumptions` 暴露 `signalSemantics` 与 `rebalanceBandPct`。
- 测试：`tests/test_backtest.py` 新增连续仓位、次日开盘成交（无未来函数）、再平衡带跳过、`0≠空仓`（离散 hold vs 连续清仓）、预热 NaN、per-request 实例、assumptions 用例。

### Step B — `quant_platform/rl/`（T-024，完成）
- `features.py`：训练/推理**共用**的因果滚动特征（`build_features` + `expanding_zscore`）。归一化用**扩展窗口 z-score**而非拟合 scaler，杜绝未来统计量入变换；`feature_signature()` 供 manifest 绑定。
- `store.py`：模型仓库 `<root>/<run-id>/{model.zip,manifest.json}`；manifest 必填键绑定 `publicationDate/dataVersion/universeVersion/trainStartDate/trainEndDate/featureSignature/codeSha/seed/algo`；`content_hash` 完整性校验；run-id 正则 + 越界逃逸防护；原子写。
- `env.py`：gymnasium 单资产 long-only 环境，收盘动作、次日开盘成交、`log` 收益、按比例交易成本。**非照搬 FinRL 泄露脚本**；顶层 `import gymnasium`，仅经训练/推理惰性路径可达。
- `policies.py`：`RLStrategy` 实现现有 `Strategy` 协议。共享实例只有元数据：`info()`（`category=ai`、`status=experimental`、`requires_trained_model=True`；DQN=`discrete_hold`，PPO/SAC/DDPG=`continuous_target_weight`）、`validate_parameters`（要求 `modelRef`）；未训练实例 `generate_signals` 抛 `RLNotTrained`。`create_for_request` 按 `modelRef` 从 store 载入权重→一次性实例，**推理永不 fit**，且回测起点 ≤ `trainEndDate` 抛 `RLInSampleRequest`（拒绝样本内）。torch/SB3 仅在 `_load_model`/`_predict_weights` 惰性导入，缺失抛 `RLDependenciesMissing`。
- `errors.py`：类型化错误 `RLDependenciesMissing / RLModelNotFound / RLNotTrained / RLInSampleRequest`（各带 `code`）。
- 测试：`tests/test_rl_core.py`（无需 `[rl]`：特征因果性、扩展归一化因果性、manifest 往返/篡改/越界、四策略元数据、未训练拒绝、样本内拒绝、`/models` 被 `git check-ignore` 命中）；`tests/test_rl_env.py`（`importorskip("gymnasium")` + `@pytest.mark.rl`：obs 形状、动作→权重映射、确定性 rollout）。

### Step C — 训练/推理接缝（T-025，进行中）
- `rl/train.py` + console script `quant-rl-train`：从**已发布快照**（`QUANT_PUBLICATION_ROOT`，`load_publication`）取数，固定 `seed`、`torch.set_num_threads(1)`，训练→序列化→写 `/models/<run-id>`；`assemble_manifest()` 为纯函数（离线单测友好）。`train_run` 支持注入 `provider`，使训练管线在无整份发布快照时亦可被单测真实执行。
- 已验证：`tests/test_rl_train_smoke.py`（`rl` marker + `importorskip`）端到端跑通 train→save→load→infer 并断言推理逐位一致与样本内拒绝。
- **剩余**：notebook 未补；真实快照训练与样本外对比（见 §4 第 5–6 步）。

### Step D — 依赖与测试门控（T-026，完成）
- `pyproject.toml`：新增 `[rl]` extra（`stable-baselines3`/`gymnasium`/`torch`），**不进 `[dev]`** → CI 默认不装 torch；注册 `rl` marker；默认 `addopts = -m "not network"` 不变，RL 用例 importorskip 自动跳过。`quant-rl-train` 注册。

## 3. 数据完整性红线如何满足
- **无未来函数**：特征仅用 `<=t`；引擎连续分支 T 收盘决策、T+1 开盘成交；有专门移位/因果单测。
- **不伪造/补价**：env 与引擎只消费 provider 真实帧，不生成合成 OHLC。
- **离线确定性**：默认测试不触网、不依赖 torch；env rollout 固定 seed 可复现。
- **权重不入库**：`/models` 已被 `.gitignore` 命中，有断言测试。
- **拒绝样本内**：推理前校验回测起点晚于 `trainEndDate`。
- **过拟合/幸存者偏差披露**：见 §4，须与基线对比并显式披露。

## 4. 评估阶梯（转 `available` 前，逐条留证）
1. 契约/引擎单测 —— ✅（`.venv` + `PYTHONUTF8=1` 下 `pytest services/algorithms` 全绿（仅 deselect 1 个 Windows 超长 param 用例），`ruff check services/algorithms` 通过）。
2. 未来函数移位测试 —— ✅（`test_features_are_causal_no_lookahead`、连续 `next_open` 单测、以及回归修复后 `test_trading_events` 复绿）。
3. 环境确定性与惰性导入实跑 —— ✅（`[rl]` 已装入 `D` 盘 `.venv`：torch 2.14.0+cpu / stable-baselines3 2.9.0 / gymnasium 1.3.0；`test_rl_env.py` 4 项在 `rl` marker 下执行并通过：obs 形状、动作→权重、离散映射、固定 seed 逐位一致 rollout）。
4. 训练管线端到端 + 推理确定性（合成数据）—— ✅（`tests/test_rl_train_smoke.py`：经注入 provider 跑**真实** `train_run`→`ModelStore.save`→`RLStrategy.create_for_request`→`generate_signals`，两次加载对同一样本外切片产出的权重逐位一致，且 ∈[0,1]；样本内窗口被 `RLInSampleRequest` 拒绝）。**说明：该冒烟用的是固定 seed 的合成 OHLC，仅验证管线正确性，不是真实行情、不含任何收益/风险结论。**
5. 真实数据训练 + 过拟合/幸存者偏差披露 —— ✅（已用真实 AkShare/腾讯 qfq 日线端到端训练：见 §4.1；结论是**未达性能门槛**，四个 RL 继续 `experimental`）。
6. 固定区间样本外回测对比 `ma_cross`/`momentum_reversal`/买入持有并显示换手 —— ✅（同 §4.1）。seed 金标准回归 —— ✅（见 §4.2，以信号一致为准）。

### 4.1 真实数据样本外评估（2026-09-19，研究/实验，非生产结论）
- 数据：真实标的 `510300 沪深300ETF`，`ak.stock_zh_a_hist_tx(..., adjust="qfq")` 拉取，1141 根日线。
- 切分（无重叠，杜绝样本内）：训练 `2021-01-04..2024-06-28`（844 bar）；样本外 `2024-07-01..2025-09-15`（297 bar）。
- 训练：经**真实** `train_run`→PPO，seed=42，`torch.set_num_threads(1)`，`total_timesteps=15000`；权重落 gitignored `/models`（本机 `.venv/quant-cache/models/ppo-real-510300-v1`，不入库），manifest `contentHash=4a31c2a45f41`、`trainEndDate=2024-06-28`。
- 引擎级样本外回测（真实帧 provider，含佣金 .03%/印花税 .05%/滑点 .02%，收盘信号次日开盘成交）：

  | 策略 | 样本外收益 | 年化 | 最大回撤 | 夏普 | 成交笔数 | 累计买入额 |
  | --- | --- | --- | --- | --- | --- | --- |
  | PPO | **+0.97%** | 0.80% | 4.23% | 0.23 | 46 | ¥199,787 |
  | MA 交叉(5/20) | +26.00% | 21.10% | 19.78% | 1.10 | 17 | ¥968,828 |
  | 动量反转 | +12.98% | 10.64% | 10.80% | 0.90 | 6 | ¥323,351 |
  | 买入持有 | +36.96% | 29.76% | 17.07% | 1.28 | — | — |

- **诚实结论**：本次极小 PPO 在样本外**显著跑输**三个基线与买入持有；低收益来自模型大部分 bar 输出接近空仓的目标权重（保守/欠训练），并非稳健 alpha。**据此不得**把任何 RL 转 `available`，不计入 MVP，不接实盘。
- **披露**：① 幸存者偏差——用"今天存在"的单一宽基 ETF，非训练时点成分/存续名单；② 过拟合风险——单标的、单区间、`timesteps` 远未收敛，参数未调优；③ 区间依赖——样本外恰逢 2024 末–2025 上涨，趋势基线与买入持有天然占优。**要形成可用证据，需**：PIT 多资产配置、更长且收敛的训练、多区间/多种子稳健性、交易成本敏感性。
- 复现：脚本在 gitignored 研究目录（`.venv/quant-cache/research/rl_research_510300.py`），命令 `PYTHONUTF8=1 .venv/Scripts/python.exe .venv/quant-cache/research/rl_research_510300.py`（需已联网装 akshare+`[rl]`）。若要长期留档，应改写成 `docs/notebooks/` 下带披露的 notebook。

### 4.2 seed 金标准回归（真实数据，`rl_seed_golden.py`）
同一真实训练窗口（510300，`2021-01-04..2024-06-28`，seed=42，`timesteps=15000`）训练两次→分别落盘并从 store 载入，对同一样本外切片（`2024-07-01..2025-09-15`）产出目标权重：
- **信号逐位一致：True**（`np.array_equal` 全部权重相等）——训练在**功能上可复现**。
- 序列化 `model.zip` 的 `contentHash` **两次不同**（`a==b: False`）：SB3 存档含优化器/梯度/RNG 等非前向必要状态，**字节级不保证一致**。
- **约定**：金标准回归以"**确定性 `predict` 输出一致**"为准，不以权重文件哈希为准；`ModelStore.content_hash` 只用于**同一份产物的完整性/防篡改**校验，不用于跨次训练可比性。

复现：`PYTHONUTF8=1 .venv/Scripts/python.exe .venv/quant-cache/research/rl_seed_golden.py`（需联网+`[rl]`）。

**评估阶梯小结**：契约/引擎/因果/确定性单测（1–4）、真实数据端到端训练与样本外对比（5）、seed 功能金标准（6）均已执行并留证。真实数据结论是**未达性能门槛**，故四个 RL 一律停在 `experimental`，**不得**标 `available`、不计入 MVP、不接实盘；是否/何时转 `available` 由后端依据更充分证据逐个决定。
（注：`test_history_probe::test_status_and_size_fail_without_retry` 被 deselect 是 Windows 环境变量 32767 上限遇到超长 param id 的既有本地问题，Linux CI 不受影响，与本改动无关。）

## 5. 后端交接清单（`services/backend/**`，非本模块实现）
- **注册策略**：`app/services/strategies.py:22` 现硬编码 `[MACrossStrategy(), MomentumReversalStrategy()]`。改为调用
  `from quant_platform.rl import augment_registry`，对返回列表执行 `augment_registry(base, include_rl=<开关>)`；RL 以 `experimental` 暴露。`include_rl=False` 时行为与现状逐字节一致。
- **提交门槛**：`backtests.py:269` 仍要求 `info().status == "available"`，RL 默认 `experimental` → 无法经 `/api/backtests` 提交，除非后端主动把某个 RL 逐个翻 `available`（须算法侧 §4 证据齐全后）。
- **数据版本绑定（必做，防混版）**：算法层 `generate_signals` 只拿到 `prices`，**看不到** provider 的 `publication_context`/`cache_revision`，故无法自行比对"训练时数据版本 vs 本次回测数据版本"。请后端在提交 RL 回测时，将请求所用的数据上下文（`publicationDate`/`dataVersion`/`universeVersion`，见 CR-017 / T-022 的 `409 DATA_VERSION_CHANGED` 先例）与 manifest 内记录值核对，不一致即拒绝。算法侧已在载入时校验 `algo` 与 `featureSignature`（否则 `RLIncompatibleModel`），但**版本一致性最终把关点在后端**。
- **参数透传**：`app/services/parameters.py` 的 `validate_against_schema` 支持 `type/required/additionalProperties/properties/minimum/maximum/enum`。RL 的 `parameter_schema` 为 `{type:object, additionalProperties:false, required:[modelRef], properties:{modelRef:{type:string}}}`，全部落在受支持子集内，无需扩展。
- **错误码**：`app/services/errors.py` 现以 `class XxxError(ServiceError): code="..."` 定义。请新增
  `RLModelNotFound → code "RL_MODEL_NOT_FOUND"`、`RLDependenciesMissing → "RL_DEPENDENCIES_MISSING"`、
  `RLInSampleRequest → "RL_IN_SAMPLE_REQUEST"`、`RLNotTrained → "RL_NOT_TRAINED"`、
  `RLIncompatibleModel → "RL_INCOMPATIBLE_MODEL"`，并在任务失败路径（`backtests.py:131` 写 `error_code`）把 `quant_platform.rl.errors.RLError.code` 映射过去。
- **单例假设**：`app/__init__.py` 断言策略无状态单例 —— RL 经 `create_for_request` 走 per-request 实例，共享实例仅出元数据/校验，不破坏该假设。
- **测试同步**：`test_api.py` 中精确策略 id 集合、`/strategies` 键集合需随注册同步（新增 4 个 ai/experimental id）。
- **对接约定**：`POST /api/backtests {strategyId:"ppo", parameters:{modelRef:"<run-id>"}}` → 202 → 轮询 `succeeded`。

## 6. 前端交接清单（`apps/frontend/**`，非本模块实现）
- `data/application-fixtures.js`：现有 `dqn/ppo/multi_agent` 桩，缺 `sac/ddpg`；对齐为 `category:ai`、`status:experimental`。
- `StrategyPicker.vue`：按 id 补四个 RL 文案。
- 回测参数表单：RL 需选 `modelRef`（已训练权重 run-id）；无权重时禁用提交并说明"需先离线训练"。
- 展示 `assumptions.signalSemantics`，并保留过拟合/幸存者偏差披露文案。

## 7. 契约建议（`packages/contracts/schemas/strategy.yaml`，属接口变更，待三方评审）
建议为 `StrategyInfo` 增**可选**字段 `signalSemantics`，枚举 `["discrete_hold","continuous_target_weight"]`，默认 `discrete_hold`（向后兼容）。`category=ai`、`status=experimental`、id 正则 `^[a-z][a-z0-9_-]{2,49}$` 已覆盖 dqn/ppo/sac/ddpg；`backtest.yaml` 无 `additionalProperties:false`，`parameters.modelRef` 可透传。本模块**未擅改**共享契约文件，仅提出定义供前端+后端+算法共同确认。

## 8. 本地端到端验证（装 extras 后）
```
pip install -e "services/algorithms[rl]"   # 建议先从 PyTorch CPU 索引装 torch
export QUANT_PUBLICATION_ROOT=<已发布快照目录>
quant-rl-train --run-id ppo-demo --algo ppo --symbol 600519 \
  --start 2024-01-01 --end 2025-03-31 --seed 42 --timesteps 20000
# 产出 /models/ppo-demo/{model.zip,manifest.json}（不入库）
```
推理回测须选 `--start` 晚于 manifest `trainEndDate`，否则 `RLInSampleRequest`。

## 9. 回滚
CR-044 全部改动集中在 `services/algorithms/**` + 本文 + `task.md/spec/PRD/design` 登记。回滚 = revert 该分支提交：引擎 `signal_semantics` 有默认值、`_simulate` 离散分支不变，删除 `rl/` 与 `[rl]` extra、`quant-rl-train` 脚本即恢复原状；未改后端/前端/契约，无跨模块回滚面。

## 10. 历史 bug 自检（对照本仓既有缺陷，逐条核对是否会重演）
按用户要求回查 `docs/cr*.md`、`spec/PRD/design/AGENTS` 与提交 `86bad9e`（本仓真实修过的"交易日戳记到执行 bar"和"排行预热窗口"两个 bug），对照 CR-044 改动：

**已确认守住（有测试）**
- 执行日=次日 bar（非决策日）：连续分支 `trade_date` 取 `prices.index[i+1]`，`test_continuous_partial_weight_and_next_open_execution`/`_zero_target_liquidates` 断言日期。
- `0≠空仓`、预热 NaN 沿用上一目标不清仓：`test_continuous_zero_is_not_discrete_hold`、`test_continuous_warmup_nan_carries_previous_target`。
- 无未来函数（收盘决策/次日开盘成交、特征仅用 `<=t`、扩展 z-score 非拟合 scaler）：`test_features_are_causal_no_lookahead`、`test_expanding_normalisation_is_causal`、末 bar 扰动不变前值。
- per-request 实例隔离、模型状态不入共享单例：`test_per_request_instance_used_when_factory_present`；推理逐位一致（含同实例两次）见 `test_rl_train_smoke.py`。
- 拒绝样本内、推理不 fit：`test_in_sample_backtest_rejected`、`_reject_in_sample`。
- 向后兼容无 `info()` 的历史策略（曾一度破坏 `test_trading_events`）：`run()` 用 `hasattr/getattr` 守卫，全量套件复绿。
- `[rl]` 重依赖保持惰性、CI 默认不装 torch：`rl/__init__` 不 import `env`，`[rl]` 不进 `[dev]`。

**本轮新修（防"混版/载错模型"静默出垃圾）**
- 推理载入现校验 manifest `algo` 必须等于请求策略、`featureSignature` 必须等于当前特征配方签名，否则 `RLIncompatibleModel`（`policies.py:_verify_bundle`；测试 `test_create_for_request_rejects_wrong_algo_bundle`、`_rejects_stale_feature_signature`）。此前 `modelRef` 只保证"存在且哈希未篡改"，不保证"是本协议/该配方训练的那份"。

**已知边界（本轮不改，交后端 / 待三方评审 / 属既有行为）**
- **C2 数据版本一致性**：算法层拿不到 provider 的 `publication_context`，无法自证"训练数据版本==回测数据版本"，交由后端按 §5"数据版本绑定"把关（409 先例）。
- **A7 空资产静默丢弃 + 资金守恒**：`engine.py` 对 empty history `continue` 但 `cash_per_symbol=initial/N`，是**既有**、影响所有策略的行为，非 CR-044 引入；已记为独立隐患，不夹带进本 CR。
- **A6 连续分支成本/基准口径**：非 `TradingCosts` 入参会静默零成本（既有）；连续再平衡以决策收盘权益×w 为目标、以次日开盘计量当前持仓，隔夜跳空可能触发一次"回到目标权重"的再平衡——属连续语义的既定设计取舍，`assumptions` 已披露 `signalSemantics/rebalanceBandPct`。
- **F1/F2 契约**：`StrategyInfo` 新增 `signal_semantics/requires_trained_model`、`assumptions` 新增 `signalSemantics/rebalanceBandPct` **未在 `packages/contracts` 声明**；`strategy.yaml`/`backtest.yaml` 无 `additionalProperties:false`，故当前不破坏校验，但正式化需前端+后端+算法评审（见 §7）。
- **F3 后端精确集合断言**：`test_api.py` 的 id/键集合会在**后端注册 RL 后**才需同步；本轮未注册、RL 保持 `experimental`，不触发。
- **E6 `codeSha` 回退 "unknown"**：非 git 环境训练时溯源信息降级，训练/复现需在仓库内跑（已如此）。

**结论**：CR-044 的引擎/RL 改动经上述历史 bug 逐条比对，已修复本轮发现的真实缺口（E5 载错模型未校验），其余为既有行为或跨模块职责，均已登记、未静默通过。测试为**离线可复现**；真实数据训练见 §4.1（结论未达性能门槛）。
