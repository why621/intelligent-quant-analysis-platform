# CR069 全资产联合模型与研究配置排行榜验收

> 后续状态：用户已授权推送部署，云站与Pages的CR069均已上线并完成真实浏览器验收。本文保留本地阶段证据；最新状态及云隔离停牌修复见[发布记录](cr069-deployment-2026-10-15.md)。

2026-10-15：实现、正式本地训练、离线回归及真实本地页面验收完成。尚未推送、云端部署或更新GitHub Pages；当前线上仍是CR068。用户授权范围为现有数据和本地算力正式训练，不新增付费资源，上线另行确认。

## 完成内容

- 新PPO/SAC/TD3组合候选在276资产训练池随机抽取2–10只同时观察，输出共享账户资产与现金权重。新发布候选适用于当前327资产目录（300股、27ETF）内任意2–10只，而非仅旧十股池。旧四单资产模型与CR066旧组合bundle保持原范围和费用约束。
- 全目录适用范围由独立cross-asset-evaluation.json绑定模型bundle、目录版本、冻结数据版本及完整目录类型映射；缺证据、漏资产、范围篡改、训练/类型不一致均拒绝。资产目录变化需重新验收范围，不静默外推。
- 新scope允许当前研究费用与预留现金；训练成本另行披露。预留现金缩放目标风险资产权重，实际现金可因行情、成本和不成交而偏离，不承诺每天固定现金比例。
- 已确认停牌沿用最后真实特征及估值、禁止成交；默认基准首日停牌可追溯此前真实收盘。未知缺口和上市前无价格不补造，真实预热不足返回带资产原因的422 RL_INSUFFICIENT_HISTORY。每只仍需至少140根真实历史预热，研究区间须在训练/验证之后。
- 新POST /api/strategies/ranking沿用当前BacktestRequest资产、日期、资金、复权、费用、预留现金、基准和策略参数。当前策略使用用户参数，其余用明确的目录默认参数；每行逐项披露。所有行通过同一回测校验与engine；当前选中策略无效时整体报错，其他候选无法覆盖完整区间或模型不适用时解释排除原因，不回退510300。区间最多366天、至少两个交易日，按区间收益降序；传统策略允许单资产。
- 排行返回配置快照、实际评价区间、完整metrics、成本及基准，缓存绑定完整配置/默认参数/模型/行情版本；30秒协作预算、每进程2个并行计算上限及同请求合并；不能强行中断底层CPU推理。每进程最多128份缓存，临时失败不缓存，前端等待45秒且不自动重试。旧GET代表资产榜保留兼容，页面不再启动旧榜。前端手动按当前配置计算；修改配置立即标旧、禁载入，迟到响应不得覆盖新配置。排行载入恢复完整回测及模拟联动。
- OpenAPI升级0.13.0，契约、服务、前端、测试和文档同步。

## 数据及正式训练

只读复用已保存真实发布：2025-09-09至2026-09-09，publicationId=e5f794c7094c21c2ba08903c0c5697904f0d4b0f87a3312e6285f0f4c95634fe，文件SHA256=762eefd0cfcd1a6de8efd814e7cb34e9376434a9ad73ee838c02051dc360bee8。目录版本33f99e5228a81019cdfad1c72ad2b896bce6cdb2d5416b5505723d73be95503b。

316资产有完整243条共同历史（289股/27ETF）；按固定SHA256排序分层留出32股+8ETF，不用于梯度或验证选优。276训练资产（257股/19ETF）；另11资产涉及上市/已核实停牌，在真实运行评估中覆盖。训练2025-09-09—2026-07-10（200条含预热）、验证2026-07-13—08-07（20条）、测试2026-08-10—09-09（23条）。每回合48步、随机子池/槽位/窗口。

PPO/SAC/TD3各seed42、137，共六候选，每个65536步/1200秒上限，实际总393216步；均有优化器更新和真实保存加载。使用训练池内固定纯股/纯ETF/混合三组十资产的平均“收益减最大回撤”选择，各算法均选seed137；selection.json在测试之前冻结。事后核对六候选的原数据哈希、分区、seed、费用及预算与冻结方案一致。未新采集行情、未重训或改写旧模型。

以下为三个独立十资产参考组合的指标均值，不是将账户合并后的组合收益：

| 模型 | 测试平均收益 | 测试平均最大回撤 |
| --- | ---: | ---: |
| PPO | -6.8919% | 8.5117% |
| SAC | -2.2445% | 4.5418% |
| TD3 | -3.3399% | 4.6426% |

同口径含成本等权持有平均收益-3.5639%，均线目标权重基线-4.8588%。模型保持experimental；未因测试较差而换种子或隐藏结果。约一年缓存、短验证测试、当前成分股选择可能有幸存者偏差，且该测试时段曾被既有研究使用，不属于全新盲测。跨资产执行验证不等于长期超额收益认证；不能声称穷举327资产所有十资产组合。

## 验证与结果

- 三模型各40组真实组合回放（33组覆盖全部327资产、4组留出资产、3组参考组合）；反序输入结果一致。独立按实际成交重算现金、数量、逐资产市值/权重、净值及费用。额外验证0.07%佣金、0.04%滑点和25%预留现金，按开盘目标及成本资金约束复算首笔成交。
- 670 passed / 23 skipped / 16 network deselected（算法+后端+工具整合离线回归）。23项可选依赖跳过不算通过；正式ML训练、全目录评估独立记录。本轮全部改动Python文件Ruff检查、git diff --check通过；116/116前端测试通过；Vite632 modules生产构建通过，入口index-CF2H6Oqx.js。
- 实际本地Edge页面78项检查、31个真实API响应全部2xx、0浏览器运行错误；原十股外5股票+5ETF联合回测，三AI+两传统同配置排行，排行/对应回测metrics和成本一致；费用、现金、日期、资产变化过期刷新，排行载入后的回测及模拟七项配置一致。1440/390/320无页面溢出，桌面及手机截图已人工查看。
- 三模型分别2/10资产真实本地模拟共六组成功；请求自定义费用/25%现金回显一致，目标资产+现金权重和100%。本地服务使用冻结历史发布并将模拟时钟固定为发布次日，不能冒充当前线上日更或云端验收。

命令（工作树artifacts/cr065-worktree）：

```sh
# WSL既有.venv，PYTHONPATH含两模块src及工作树
PYTHONPATH=services/algorithms/src:services/backend/src:. ../../.venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools/test_universe_experiment.py -m 'not network' --disable-warnings --maxfail=3
node --test apps/frontend/tests/*.test.js
VITE_API_BASE_URL=/api node ../../node_modules/vite/bin/vite.js build apps/frontend --outDir ../cr069-universe/dist
# 现有Windows ML依赖（训练无网络），先按实际路径设置PYTHONPATH
python tools/prepare_universe_experiment.py --publication ../../artifacts/cr024-publication-20260910 --output <全新实验目录>
python -u tools/train_universe_candidates.py --experiment <实验目录>
python -u tools/evaluate_universe_candidates.py --experiment <实验目录> --publication ../../artifacts/cr024-publication-20260910
# 原根目录，本地隔离服务18769
node artifacts/cr069-universe/browser.cjs
```

现有证据在原根ignored artifacts/cr069-universe：experiment/plan.json、training-report.json、selection.json、evaluation-report.json、models各权重/manifest/validation/cross-asset-evaluation与逐笔replays、models/release.json；browser.json、六组排行、两个本地任务、linked-allocation.json、joint-allocation.json及桌面/手机截图。真实行情、模型、任务库及个人凭据不入Git。

验收过程修复了历史不足错误映射、首日确认停牌基准估值、候选续跑身份验证及独立逐资产权重复算。最初以“预留后成交数量必为未预留的75%”作检查忽略未预留账户的手续费缩量，已改为核对真实目标权重缩放及独立资金可负担计算；保留全部账本/费用检查，完整真实评估随后通过。数据准备首次遗漏目录分页limit，已改完整目录并重新冻结；既有输入未覆盖。

## 未完成事项与下一步

本地候选已经可评审。尚未推送、上传权重、云隔离回归或切换线上；用户要求上线另行确认。获后续授权再准备仅含源码/前端/新候选模型的发布包，隔离核验旧新策略、日更模型依赖隔离、备份和回滚，再部署云端与Pages。07:30日更、线上历史任务和真实行情本轮未修改。
