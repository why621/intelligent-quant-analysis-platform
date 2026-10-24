# CR072 业务需求与算法提供审计（2026-10-24）

## 结论

基线为已合并PR #57的main d3ba2d7。本轮用户授权审查需求对应并删除有明确完整替代关系的算法；未授权推送/发布。本轮不训练、不修改生产模型或行情。

核心五模块及CR065–071功能已实现，不能扩展成“全部原始要求及研究目标均已满足”。当前六组合模型不满足REQ-11所写的三年以上训练、一至两年验证窗口；后续短窗口发布计划已获授权，但没有据此证明原长窗口目标完成。数据仍有一只未知缺口，性能泛化/长期超额收益无充分证据。

十二个当前入口中，没有找到业务能力完整覆盖且有充分优势证据的替代关系，因此删除0个。不以复杂架构、算法名称或短窗口收益高低决定删除；这执行的是用户的条件删除要求，不是忽略删除授权。

## 逐需求映射

| 需求 | 对应实现/检查 | 结论和边界 |
| --- | --- | --- |
| REQ-01 可追溯资产池 | data/universe.py、data/publication.py；目录分页/搜索及AssetPicker；asset_catalog测试 | 已实现固定300股票+27ETF目录及版本身份。是当前名单快照，不是逐历史时点指数成分；不能将327目录称全部A股。 |
| REQ-02 日线与质量 | data/coverage.py、publication.py、历史读取/交易事件检查；coverage及publication测试 | 已实现完整区间核验、上市/停牌与未知缺口区别。10月24日只读确认326/327完整，601059仍unknown，不能宣称所有资产全区间均可计算。 |
| REQ-03 指数与基准 | backtesting/engine.py及shared_backtest测试；API明确index:CSI:000300 | 已实现独立沪深300价格指数及默认所选资产买入持有。默认基准初始等权、不再平衡、不计费用，不是含分红全收益指数，也非与策略完全同成本口径。 |
| REQ-04 概况 | data/overview_worker.py、test_overview_degraded.py | 已实现沪深300日频概况；本次299/300有效样本，日期2026-10-23，明确部分覆盖，非全市场/盘中实时。 |
| REQ-05 相关性 | analytics/correlation.py、相关性API、前端research测试 | 已实现2–10资产、收益日期对齐及不足拒绝，10资产45对；相关性不是因果或未来收益预测。 |
| REQ-06 回测 | backtesting/engine.py、portfolio执行层、rl/portfolio_strategy.py、异步任务服务；shared_backtest/research_inputs测试 | 已实现默认基准、真实买卖点/持仓曲线/费用、请求快照与恢复。六组合run_joint共用一个PortfolioEpisode并联合输出权重，不是独立账户净值拼接。旧单资产与旧接口兼容不冒充联合模型。 |
| REQ-07 排行 | backend/services/ranking.py、test_research_ranking.py、前端use-ranking.js | 已实现当前组合/日期/资金/现金/成本/基准比较，同请求复用回测引擎；当前策略用当前参数，其他策略用披露的默认参数。八项排行为正常兼容组合场景，不保证缺数据时仍有八项。旧GET固定510300只保留兼容。 |
| REQ-08 模拟配置 | allocation.py、backend/services/allocation.py、use-allocation.js及workflow测试 | 传统策略1–10资产，六组合2–10；按同配置重放至最新有效发布日、形成下一交易日目标，现金+资产守恒，过期拒绝。四旧单资产不支持模拟；历史回测结束日不等于当前模拟依据日。 |
| REQ-09 失败恢复 | publication上下文、模块capability、data-recovery、持久化任务/版本检查 | 已实现旧快照保留、版本冲突拒绝、任务恢复和未知缺口明确报错。缺口本身未因此解决；不能通过填零/补价掩盖。 |
| REQ-10 公网与运维 | Pages工作流、CORS、发布/备份脚本、CR067/071验收 | 已有两站完整浏览器与保留审计证据；本轮仅4个公网GET及离线回归，不能称重跑全部云端回归。当前数据updatedAt为10月24日07:59，但本轮未读取timer/journal，不能单靠此时间断言定时任务全过程通过。 |
| REQ-11 长窗口RL | rl/splits.py、单资产manifest；组合portfolio_policy.validate_splits | 部分满足。旧单资产训练2015-01-05至2018-06-30；验证2018-07-01至2021-12-31按CR059多折修订，非简单违反原验证上限。六组合训练2025-09-09至2026-07-10、验证2026-07-13至2026-08-07，不满足长期窗口目标，也未有等价多市场阶段验证。组合时间检查只保证顺序/不重叠，不等价旧单资产长窗门禁。 |

CR065–071增量检查：相关性→回测→模拟单向默认同步、手动脱离与恢复、运行中请求不可改、参数变化使排行过期，均有实现与回归。EarnMore增强已包含共享注意力、掩码重建、随机子池及训练内换池；网页仍回测固定所选组合，不是网页动态换股池或完整论文复现。没有把这些未承诺能力判为实现缺陷。

## 十二策略逐项判定

| 当前策略 | 业务角色 | 替代判定 |
| --- | --- | --- |
| 均线交叉 | 可解释趋势规则、回测流程基础对照 | 保留。RL缺少已证明的稳定收益优势，也不能取代规则可解释性。 |
| 动量反转 | 超买卖出/超卖买入的反转规则 | 保留。与均线趋势逻辑不同，不是重复实现。 |
| 单资产DQN | 510300离散空仓/保持/满仓决策、历史实验复现 | 保留。组合模型至少两资产，无法覆盖该单资产用途。 |
| 单资产PPO | 510300长窗口连续权重实验 | 保留。增强组合PPO的训练窗口和资产数要求不同。 |
| 单资产SAC | 510300长窗口连续权重实验 | 保留。增强组合SAC不构成同业务完整替代。 |
| 单资产TD3 | 510300长窗口确定性连续权重实验 | 保留。组合TD3不支持原一资产请求。 |
| 普通组合PPO | 共享账户2–10资产，MLP表示，增强方法对照 | 保留。增强PPO表示机制更丰富，但尚无充分同配置独立评估证明全面优胜。 |
| 普通组合SAC | 同上，SAC学习机制 | 保留。增强SAC历史参考结果不能证明所有组合/时期优于普通SAC。 |
| 普通组合TD3 | 同上，TD3学习机制 | 保留。增强TD3验证组差异明显，缺少完整优势证据。 |
| 增强组合PPO | 掩码注意力+新鲜轨迹PPO | 保留。与SAC/TD3不同的训练路径，不互为替代。 |
| 增强组合SAC | 掩码注意力+经验回放SAC | 保留。短历史参考收益较好不构成删除其他算法的依据。 |
| 增强组合TD3 | 掩码注意力+确定性策略/双Q/延迟更新 | 保留为实验。验证股票组-20.926%、混合组+16.249%，不能称默认最佳或稳定盈利。 |

普通组合观测为固定槽MLP，训练随机槽位；增强版为共享注意力、无股票代码/槽位身份。服务对输入顺序的规范化与架构本身的排列等变是不同性质，不能因为服务反序测试通过就说普通MLP具备注意力模型的结构性质。

DDPG是最接近“已有后继、无需继续新增入口”的历史情况：代码还保留兼容注册，但默认研究列表RESEARCH_ALGOS已改为PPO/DQN/SAC/TD3，当前线上十二策略中没有DDPG。无需再删除一个不存在的线上入口；删加载白名单会损害历史权重复现，不属于本次当前入口精简的必要步骤。

## 发现的问题与处理

1. 长窗目标与组合短窗交付之间有未闭合差距：登记研究待办，不伪造已完成，不突然禁用已经按短窗计划授权上线的六模型。后续需先明确组合长窗目标并准备有证据的深历史、多阶段/多种子及未使用窗口评估，另行登记训练预算。
2. 601059的未知数据缺口仍在：本次API显示末行情2026-09-14，10月19–23日列为缺口。这里只核查现状，不推断停牌/源站根因、不自行采集或修改线上。
3. 模拟页面错误提示仍写“现有AI模型仅支持实验回测”：已本地改为“当前所选策略尚不支持模拟配置。请选择列表中支持模拟的传统策略或多资产组合模型。”保持基于allocationEnabled/status的能力检查不变，无接口变更。
4. PRD/design/spec前部CR050章节仍称“当前”，其中独立拼接、固定510300排行与现实现相反：改为明确历史章节，并指向本次矩阵；保留历史过程证据。
5. 十二入口平铺较拥挤是产品组织问题，不是模型被替代的证据。可后续按传统/单资产/普通组合/增强组合分组或折叠，但本次未获具体分组需求，不扩展实现。
6. 旧单资产训练奖励税费与网页ETF回评税费差异已有披露；这是可比性限制，不应作为未披露的同成本试验。组合模型当前请求的回测/排行/模拟成本已统一，调成本也不等于重新训练。

## 验证与证据

- 本轮算法/后端/工具离线：688通过、26可选依赖跳过、16网络测试排除，33.55秒。XML：artifacts/cr072-audit-20261024/regression.xml；日志/tmp/cr072-regression.txt。跳过不算通过。
- 前端118测试通过及Vite构建通过；提示改动是文字修复，未新增镜像实现的测试。日志/tmp/cr072-frontend.txt、/tmp/cr072-build.txt。
- 公网只读4 GET：health、data/status、strategies、market/overview均成功。12策略、6组合allocationEnabled=true；传统策略由status=available允许模拟，不能因缺可选allocationEnabled字段误判不支持。publicationDate=2026-10-23，dataVersion=16a40d4fd6a44e04ca34060a1db5cd7659de93b80fc9600fc64086c0d1262c25，326/327历史及299/300概况。原始响应仅保存在ignored artifacts/cr072-audit-20261024/public-readonly.json。
- 本地真实权重/冻结行情重放通过：12策略、20成功回测、12模拟、8排行、5配置。使用Flask test client、Windows临时DB并拦截socket连接；六组合2/10资产与反序验证、排行/费用一致。模拟时钟固定于冻结行情次日，绝不当作当前线上模拟验收。证据artifacts/cr072-audit-20261024/local-models/report.json。命令：tools/verify_masked_extensions.py --publication ../../artifacts/cr024-publication-20260910 --rl-release ../cr062-release/models/rl-release.json --model-roots artifacts/cr071-local-03/models --output artifacts/cr072-audit-20261024/local-models（Windows原生Torch及既有依赖路径）。
- 既有云站/Pages/权重训练证据见CR069、CR070、CR071报告；本轮不重复训练，不基于历史测试再选模型，不宣称收益优势。

命令：WSL `PYTHONPATH=services/algorithms/src:services/backend/src:. ../../.venv/bin/python -m pytest -c services/algorithms/pyproject.toml services/algorithms/tests services/backend/tests tools/test_universe_experiment.py --disable-warnings --maxfail=3 -o addopts="-m not\ network" --junitxml=artifacts/cr072-audit-20261024/regression.xml -q`；`npm test --workspace @intelligent-quant/frontend`；`npm run build --workspace @intelligent-quant/frontend`。

本轮无算法删除、无契约变更、无Git推送、无部署、无生产写入。长期绩效、组合长窗口、缺口根因仍未解决，不标完整目标全部完成。

### CR072 GitHub推送与Pages发布登记（2026-10-24）
用户当次授权“推送部署到GitHub”。发布范围仅本轮需求审计/SDD文档及模拟配置错误提示修复；没有算法删除或模型变化。新增T-CR072-5：检查差异、Pages生产构建、推送codex/cr072-requirements-audit；main合并后核验对应Pages工作流及静态提示。沿用本轮688后端/算法与118前端测试及真实模型本地重放证据，不把它们当作本轮云端发布验收。云API/模型/行情/任务库和日更不作修改。main受保护且当前无GitHub API合并权限，推送后由用户创建合并PR；合并前不标Pages已部署。

### CR072 合并与Pages静态验收完成（2026-10-24，接续实测）
T-CR072-5完成。GitHub API确认PR #59已合并，main为10b31aeb599ea7374253f8539201ffecad6fba69，父提交包含f6db8a55ddae26fe029a9311f8837b3ecc34515b。对应Pages工作流40064032891、Frontend CI 40064032764、Regression stack CI 40064032817均completed/success。
真实Edge打开Pages并用fetch(cache=reload)/Web Crypto逐文件SHA256核对，12个公网静态文件均与CR072 dist-pages一致；入口assets/index-DGsMOs9S.js。相同哈希的入口包含完整新提示，不含“现有AI模型仅支持实验回测”。本次为提示改动的公网静态验收，没有重跑全业务交互或创建线上回测/模拟，不声称重新验收云端日更、行情或模型收益。
命令：WSL git status --short / branch --show-current / log -1 --oneline / diff --stat / ls-remote origin；PowerShell Invoke-RestMethod读取GitHub commits及actions/runs；在活动树执行node artifacts/cr072-audit-20261024/verify-pages-hashes.cjs。证据为ignored artifacts/cr072-audit-20261024/pages-browser-file-hashes.json，脚本同目录可复现。初次脚本从根工作区启动导致MODULE_NOT_FOUND，改为活动工作树后成功；Windows受限网络调用失败后经执行权限审查完成只读验证，不属于线上故障。
本轮只追加本地文档，保留原交接与task修改，未提交、推送、训练或部署。REQ-11组合长窗、长期超额与池外泛化、601059未知缺口仍未完成；本轮未重查缺口现状。后续这些工作需分别登记范围、验收与预算，不能因发布完成而一并关闭。
