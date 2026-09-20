# CR-045 PR29 修复与验证（2026-09-20）

## 交付范围

用户授权根据 PR29 审阅问题修复分支、确认能运行后提交。基线 `algorithm/rl-strategies` / `366742a360945643635082a07ac0402ab5410454`，修复分支 `codex/fix-rl-review-20260920`，工作树 `artifacts/fix-pr29`。原工作区的审阅报告与 task.md 修改保留，未混入本批提交。

本批修复 R1–R4，新增共享执行内核、严格模型元数据格式和回归；RL 仍 experimental，未注册前后端、未改变 HTTP 契约、未采集行情、推送、部署或修改线上数据。

## 实现与验收对应

- R1：引擎对提供 `prepare_inference` 的策略逐 bar 传入实际成交账户仓位，再执行下一开盘交易。本金、佣金、印花税、滑点、再平衡阈值均来自本次请求。原静态策略仍通过 `generate_signals`。独立 RL `generate_signals` 只是默认 100000 元/默认费用的研究便捷入口，也使用同一引擎；正式请求不预生成虚拟账户信号。
- R2：训练环境和回测共用 `backtesting/execution.py`。连续买入先用 cash/(1+commission) 限制成交额，余款仅清理浮点残差；无现金不能买入。DQN 复用原离散引擎买入/清仓语义，连续全仓不引入借款。训练环境默认本金/费用/阈值与默认回测一致，也可显式传参。
- R3：manifest `schemaVersion=2`；保留权重 `contentHash`，新增 `bundleHash` 覆盖规范化完整元数据与权重。加载校验字段/类型/seed/日期顺序/发布日/runId/字节数/哈希；空训练截止日明确拒绝。新增 `executionVersion=account-feedback-v2`，旧模型不得自动补字段或补哈希变成可用，必须重新训练。哈希是一致性校验，不是抵御有写权限攻击者重算哈希的签名。
- R4：在环境构造/推理前校验有序、唯一、正且有限的 OHLC 和样本数；默认 20 根预热要求至少 22 根观测。0/1/20/21 根在直接推理和引擎入口均抛 `RLInsufficientHistory`，22 根可完成一次决策/下一 bar 成交。不填补缺日，provider 的覆盖门禁保持。

测试以成交记录独立重建现金/份额核对模型观测，覆盖四策略、三组本金/费用/阈值；训练环境与引擎每一步净值对账；满仓/重复全仓/费用/跳空均检查现金和仓位。元数据改值、删除、错误日期、空日期、旧执行版本和新旧 hash 绑定都有失败或成功对照。

## 实际验证（本轮证据，不累计为历史成果）

环境：WSL Ubuntu、Python 3.12.3。基础解释器使用仓库 `.venv/bin/python`；ML 包仅安装在 `artifacts/rl-fix-deps` 和 `artifacts/rl-fix-extra-deps`，不修改共享 venv，不纳入 Git。CPU torch 2.14.0+cpu、stable-baselines3 2.9.0、gymnasium 1.3.0。

命令均从修复工作树执行：

1. `PYTHONPATH=services/algorithms/src:services/backend/src ../../.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -q -o addopts= -m "not network"`：**387 passed、2 skipped、8 deselected，16.37 秒**。两处 skip 为未暴露可选 RL 依赖的环境/训练模块，network 用例未运行。
2. `PYTHONPATH=../rl-fix-extra-deps:services/algorithms/src ../../.venv/bin/python -m pytest services/algorithms/tests/test_rl_env.py services/algorithms/tests/test_rl_review_regressions.py -q -o addopts=`：**58 passed，1.26 秒**，其中 17 项 Gymnasium 环境用例、41 项缺陷回归。41 项已包含在上一条 387 项中，不重复累计。28 条原有 Box float64→float32 空间精度提示，不是计算错误。
3. `PYTHONPATH=../rl-fix-deps:../rl-fix-extra-deps:services/algorithms/src:services/backend/src ../../.venv/bin/python -m pytest services/algorithms/tests/test_rl_train_smoke.py -q -o addopts= -rs`：**5 passed，13.05 秒**。DQN/PPO/SAC/DDPG 各运行实际 SB3 learn/save/load/predict，验证重复推理一致、v2 bundle、带非默认成本/本金的引擎回测；另有样本内拒绝用例。10 条上述 Box 精度提示。使用固定种子的明确合成 OHLC，不代表真实行情、策略收益或长期稳定性。
4. `../../.venv/bin/python -m ruff check services/algorithms`：**全部通过**。
5. 原 PR `test_backtest.py` 的 EOF 多余空行已清理；提交前 `git diff --check` 通过；空历史引擎入口补断言后 41 项缺陷回归再次通过（1.14 秒），全算法 Ruff 仍通过。

先前首轮 41 项引擎/核心测试和环境独立检查也通过，均是上述测试的子集，不叠加计数。四类验证合计覆盖 409 个不同离线用例；完整训练已实际运行，不以 importorskip 冒充成功。

## 使用、迁移与后续边界

安装项目 `[rl]` extra 后，现有 `quant-rl-train` / `python -m quant_platform.rl.train` 训练入口会生成 v2 manifest；使用新的 run-id 重新训练旧模型。不要手动升级旧 manifest 的 schemaVersion/executionVersion。推理仍必须晚于 trainEndDate，模型和真实数据不得入库。

新增算法错误 `RL_INSUFFICIENT_HISTORY` 与既有 `RL_INCOMPATIBLE_MODEL` 需在后端将来注册 RL 时映射；本批未暴露新 HTTP 功能。历史 CR044 文档中的旧执行行为/旧实验收益不是本实现的新证据。真实数据评估、跨版本数据绑定的后端接入、notebook 与正式 available 门槛保持后续事项。

回滚需要整体撤销执行内核、策略回调、模型格式和对应测试；不能仅回滚读取器继续使用 v2 新语义权重。本轮未改线上数据，无云端回滚动作。

本批交付为修复分支上的本地 Git 提交；未推送或合并原 PR。提交标识以该分支 Git 历史和本轮最终答复为准。
