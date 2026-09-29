# CR-059/060 交付：后端 / 前端待办清单（2026-09-29）

配套文档：`docs/cr060-rl-deployment-note-2026-09-29.md`（发布条目、费率口径、效果口径）。
范围：算法侧交付 4 个模型，其余工作由后端 / 前端完成。算法侧不改后端、前端与 `packages/contracts`。

## 交付内容

云端 36 个 run 中**验证窗选出的最优 4 个**（每算法一个，全部 510300）：

| algo | run-id | bundleHash | 折中位数得分 |
| --- | --- | --- | --- |
| ppo | `ppo-510300-s42` | `e2052d6fc82a2d7517903059159cd2bb1e34110422b13ab26a6a08e4ec2f0c40` | −1.0245 |
| dqn | `dqn-510300-s42` | `bb5e886470e5e724d53a90527ca73941c579186415225f177a4485d9c857e036` | +0.2122 |
| sac | `sac-510300-s43` | `53970ac53673bcf4bb43ee66c32dac9fde83fe83d1ae3377af05d314b8823a96` | −1.0273 |
| td3 | `td3-510300-s44` | `33104a2e452386c950fd684e532eb6327e7f17449b2decca024887404c688f82` | −0.2939 |

每个目录 = `model.zip` + `manifest.json`。布局必须为 `<models root>/<run-id>/{model.zip,manifest.json}`。

## 后端待办

| # | 待办 | 阻塞级 | 代码锚点 | 验收 |
| --- | --- | --- | --- | --- |
| B1 | 对齐 universe 闸门：让运行时 `publication_context["universeVersion"]` 与 manifest 的 `research-backfill-root` 相符（重训在发布快照上，或授权做发布快照登记） | **是** | `app/services/rl.py:191-193`；算法侧 `rl/train.py:232`；`data/publication.py:198` | 一次真实请求返回 200，而非 `RL_INCOMPATIBLE_MODEL`(universe mismatch) |
| B2 | 写发布文件并配置 `QUANT_RL_RELEASE`（单文件；4 条，每条 `{algo,modelRef,bundleHash,symbols,adjust}`；`symbols==["510300"]`、`adjust=="qfq"`） | **是** | `app/__init__.py:88`；`app/services/rl.py:45-79` | `load_web_models` 不抛错，得到 4 个 WebRL 实例 |
| B3 | 权重就位：4 个目录放到 **release 文件同目录** | **是** | `app/services/rl.py:87`（`ModelStore(release_path.parent)`） | `ModelStore.load()` 4 个全过，且 `bundleHash` 与发布文件**逐字一致** |
| B4 | 补标的校验：请求标的必须在 `release["symbols"]` 内（现在只查行情够不够） | 否（正确性） | `app/services/rl.py:194-198` | 用 510050 请求 510300 模型被明确拒绝，而非静默出信号 |
| B5 | 回评费率：`backtests.py` 默认 `stampDutyPct=0.05`，对 **ETF 是错的**（ETF 不缴证券交易印花税）→ 对 ETF 传 `stampDutyPct: 0` | 否（数字正确性） | `app/services/backtests.py:356-359` | 回评费用与配套文档 §2 的 ETF 口径一致 |
| B6 | RL 策略状态：`status="experimental"` 写死在算法侧，是否放开由后端决定 | 否 | `rl/policies.py:205` | 网页上 4 个 RL 策略可用状态符合预期 |

## 前端待办

| # | 待办 | 代码锚点 | 验收 |
| --- | --- | --- | --- |
| F1 | 渲染 4 个 RL 策略（每个策略只有一个 `modelRef`，**不需要模型选择器**），并展示模型上下文（`outOfSampleStartDate` / `symbols` / `crossAssetValidated=false`） | 后端 `rl.py:136-150, 152-173` | 4 个策略可选中、能发起回测、样本外起始日提示正确 |
| F2 | RL 策略下资产需锁 510300（或依赖 B4 拦截），给出明确提示而不是 500 | — | 选其它资产时提示"该模型仅支持 510300" |
| F3 | 展示免责说明：权重来自研究回填缓存（`research_backfill_unpublished`）、**未证明超额能力** | 配套文档 §4 | 页面有该说明，且不出现"跑赢基准"类表述 |

## 端到端验收

1. 网页对 510300 跑一次 RL 回测 → 出净值 / 成交 / 费用。
2. 请求窗口落在样本内（起始 ≤ 2021-12-31）→ 被拒（`RL_IN_SAMPLE_REQUEST`）。
3. 请求未部署的 `modelRef` → 被拒（"仅可选择网页已部署模型"）。

## 效果口径红线

**不得声称这 4 个模型有超额能力或通用性。** 依据：三标的 deflated Sharpe 门槛 0.9808，实测 0.122 / 0.604 / 0.346 全部未过门（510300 的 `minTrackRecordLength` ≈ 182 年）；验证窗选优中位数输给 ma_cross / momentum；跨标的迁移实测胜率 31–51%（≈抛硬币）。可直接引用的结论句：**此数据规模下未证明 RL 超额能力**。

## 已知未修缺陷（不阻塞交付，但须知情）

- **缺陷 #5**：推理不校验请求标的 == 训练标的（算法侧与后端各一半，B4 是后端那半）。
- **CR-061**：训练奖励未透传费率（固定吃含印花税的 0.15% 往返）、ETF 被计印花税且无日期变化。修它会使既有全部权重失效、须重跑，**本轮不实施**。