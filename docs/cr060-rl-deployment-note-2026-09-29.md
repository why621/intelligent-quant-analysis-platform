# CR-059/060 RL 上线说明（算法侧 handoff，2026-09-29）

范围：把本轮 36-run 网格里验证窗选优出的 **4 个 510300 模型**交给后端发布。
RL 仍为 `experimental`，只有后端能改状态；本文件不改后端、前端与 `packages/contracts`。

## 1. 发布条目（4 条，一算法一条）

`QUANT_RL_RELEASE` 指向的发布文件（schemaVersion 2），权重目录放在**该文件同目录**：

```json
{"schemaVersion":2,"models":[
 {"algo":"ppo","modelRef":"ppo-510300-s42","bundleHash":"e2052d6fc82a2d7517903059159cd2bb1e34110422b13ab26a6a08e4ec2f0c40","symbols":["510300"],"adjust":"qfq"},
 {"algo":"dqn","modelRef":"dqn-510300-s42","bundleHash":"bb5e886470e5e724d53a90527ca73941c579186415225f177a4485d9c857e036","symbols":["510300"],"adjust":"qfq"},
 {"algo":"sac","modelRef":"sac-510300-s43","bundleHash":"53970ac53673bcf4bb43ee66c32dac9fde83fe83d1ae3377af05d314b8823a96","symbols":["510300"],"adjust":"qfq"},
 {"algo":"td3","modelRef":"td3-510300-s44","bundleHash":"33104a2e452386c950fd684e532eb6327e7f17449b2decca024887404c688f82","symbols":["510300"],"adjust":"qfq"}]}
```

- 目录布局：`<release 文件同目录>/<run-id>/{model.zip, manifest.json}`（后端 `WebRL` 用 `ModelStore(release_path.parent)`）。
- 4 条满足后端"每个算法一条"的约束；`symbols==["510300"]` 也满足现有硬校验，**不需要改发布 schema**。
- **不含** 510050 / 159922（后端 `rl.py:84` 硬校验 `symbols==["510300"]`，发了也会 `ValueError`）；不含 `ddpg`（本轮无新权重）。

每个 manifest 的关键字段（4 个全同）：`executionVersion=account-feedback-v2`、`featureSignature=29ce5f44980b8c8c`、`bandPct=0.02`、`weightSelection=validation-best`、`consistency=research_backfill_unpublished`、`universeVersion=research-backfill-root`、训练窗 `2015-01-05..2018-06-30`、验证窗 `2018-07-01..2021-12-31`、留出窗 `2022-01-01..2024-12-31`。本地已实测 4 个都能通过 `RLStrategy.create_for_request` 的加载闸门。

## 2. 费率口径（必须随发布一起说明）

引擎（`backtesting/execution.py`）的实际计费：**佣金买卖双边各 0.03%、印花税仅卖出 0.05%**，滑点体现在成交价里、**不计入 `fees_cny`**。故每往返：

| 配置 | 计入 `fees_cny` | 另有滑点 | 经济往返成本 |
| --- | --- | --- | --- |
| 默认 `TradingCosts`（含印花税） | 0.03×2 + 0.05 = **0.11%** | 0.02×2 | ≈ **0.15%** |
| `--stamp-duty-pct 0`（ETF 正确口径） | 0.03×2 = **0.06%** | 0.02×2 | ≈ **0.10%** |

**两个口径当前不一致，这是 CR-061 缺陷，未修：**

- **训练奖励固定用默认 0.15% 往返**（`train.py:360` 构造 `TradingEnv` 时未传成本参数，`env.py:106` 落到默认 `TradingCosts`）——`--stamp-duty-pct` **不影响训练**。证据：同一权重在 15bp 探针与 10bp 网格下 `foldScores`/`bestEvalReward` **逐位相同**。
- **本轮网格的评分/CSV 用 `--stamp-duty-pct 0`**，即表里所有数字按 **0.10% 往返**口径。
- 同一权重实测（`ppo-510300-s42`，300 笔成交）：15bp → test **−1.5814%**、fees **¥7,532.46**；10bp → test **+2.1068%**、fees **¥4,198.21**（fees 比 0.557 ≈ 0.06/0.11，与上式吻合）。

**线上建议口径**：本批 3 个标的（510300/510050/159922）**全是 ETF**，按《印花税法》第三条证券交易印花税只覆盖"股票和以股票为基础的存托凭证"，ETF **不应计印花税** → 线上回评应使用 `--stamp-duty-pct 0`（0.10% 往返）。同时须写明：**权重是在含印花税的 0.15% 奖励下学出来的**，即模型对交易成本的估计比实际偏高，换手倾向偏保守；这会让线上口径下的回测数字略优于训练时优化的口径。

## 3. 上线阻塞项（与效果无关，必须先解决）

1. **universe 闸门**：`validate_web_request`（后端 `rl.py:191-193`）要求运行时 `publication_context["universeVersion"] == manifest["universeVersion"]`；manifest 为 `research-backfill-root`，线上 provider 给的是发布快照 `snapshotId`（`publication.py:198`）→ **必然 mismatch，请求被拒**。需（a）用发布快照数据重训，或（b）授权做一次发布快照登记。
2. **缺陷 #5 未修**：算法侧 `_verify_bundle` 只校验算法/特征签名/band/成交版本，**不校验标的**；后端 `validate_web_request` 也只校验请求标的的行情，**不校验它在不在 `release["symbols"]` 里**。只发 510300 时风险受限，但建议后端补一行 `symbol in release["symbols"]`。
3. **RL 状态**：`status="experimental"` 写死于算法侧 `policies.py:205`，放开需后端决定。

## 4. 效果口径（不要超出证据说话）

按 CR-059 判定规则，本批模型**不得声称超额能力**：三标的 deflated Sharpe 门槛 0.9808，实测 0.122 / 0.604 / 0.346，**均未过门**；510300 的 `minTrackRecordLength` 为 **45,808 根 ≈ 182 年**。验证窗选优中位数 −10.75% / −14.43% / −7.36%，**输给最好技术基准**（ma_cross −1.41% / momentum +4.47% / ma_cross +14.00%）。跨标的迁移实测（本轮新增，见 §5）同样未显示通用性。结论句：**此数据规模下未证明 RL 超额能力**。

## 5. 通用性实测（2026-09-29，本地离线，零取数）

用网格同一套引擎/基准/成本复算，脚本 `data/research_history/_cloud_cr060/xfer_probe.py`（gitignored 草稿）。

- **跨标的（2022-01-01..2024-12-31）**：把 4 个 510300 模型分别跑到 510050、159922 上（8 格）。胜买入持有 3/8、**胜 ma_cross 1/8**、胜 momentum 2/8。同模型在自己标的上明显更好（如 ppo 510300 −1.58% vs 510050 −15.09%、159922 −13.54%）。
- **平台缓存 45 只股票（2025-07-23..2026-09-18，284 根）**：180/180 格全部跑通。该窗买入持有中位 +0.93%（25/45 上涨）、ma_cross 中位 −6.31%。

| 模型 | RL 中位 | 胜 ma_cross | 相对 ma_cross 超额中位 |
| --- | --- | --- | --- |
| ppo-510300-s42 | −5.66% | 23/45 (51%) | +0.73pp |
| dqn-510300-s42 | −12.40% | 14/45 (31%) | −6.68pp |
| sac-510300-s43 | −5.87% | 22/45 (49%) | −1.92pp |
| td3-510300-s44 | −2.42% | 18/45 (40%) | −1.56pp |

**读法：胜率在 31–51% 之间，等于抛硬币；四个模型的中位收益全为负，且全低于同窗买入持有。结论：本批模型不具通用性。** 注意该窗仅 284 根（扣 140 根预热后实际决策约 144 根）且距训练窗已 7 年，属弱证据，但方向与留出窗结论一致。

## 6. 产物与校验

- 拉回本地：`data/research_history/_cloud_cr060/`（`models_cr060/` 166M 含 36 run + `_grid/` + `_trainlogs/`；`models_ppo_probe/`；`models_algo_smoke/`；`logs/`）。
- 校验：模型侧 **147 个文件**（36 model.zip + 36 best_model.zip + 36 evaluations.npz + 36 manifest + 网格 3 件）sha256 与云端**逐位一致**；7 个日志文件哈希一致。
- 云端留档：`/root/quant/data/research_history/{models_cr060,models_ppo_probe,models_algo_smoke}`、`/root/{grid-main,grid-ppo,grid-smoke,install,suite,rl_only}.log`、`/root/progress.sh`；代码 commit `95c9290`。

## 7. 后端 / 前端待办清单

见独立文件 **`docs/cr060-handoff-todo-2026-09-29.md`**（含交付内容、B1–B6 / F1–F3 待办、端到端验收、效果口径红线、已知未修缺陷）。该文件即交给后端/前端的清单。