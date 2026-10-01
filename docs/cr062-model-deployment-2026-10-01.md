# CR062 新模型上线记录


## CR062 新模型发布集成（2026-10-01，登记）
用户交付cr060-best4并明确要求继续至上线。基线main dd96ea3 + CR058 dc8186c + 算法分支9ae583c（权重训练代码95c9290），合并spec/task追加记录冲突时两侧历史均保留。候选为PPO/DQN/SAC/TD3四个510300权重；不伪装为旧DDPG，不重训、不采集。逐个哈希/元数据/加载推理验证，兼容新版特征140根预热及验证窗，以实际常量为准；候选不合格不切换。
研究来源保持原manifest，增加显式可信发布配置绑定目标universeVersion及模型哈希，仅对已核验的510300研究模型开放；请求其它资产明确拒绝，新源记录不能借放宽旧闸门混入。兼容保留旧发布schema但不强行运行旧特征权重。发布后四个实验模型继续experimental，披露未证明超额/通用性、训练费率与回评不同；仅对本批ETF研究强制stampDutyPct=0，统一排行/回测口径，不静默改股票税率或重训奖励。API/前端同步来源、范围、动态预热及费用说明，保留CR058区间展示。
验收：离线全量与反例、四bundle只读实际加载/真实行情推理、候选五模块及四模型异步任务、样本内/错模型/错资产拒绝、任务库备份实际恢复与行情/日更账本保留、云HTTPS/Pages桌面移动验收。GitHub遵循PR和Pages工作流，不能绕过保护。全部只对有证据的步骤标完成。

## CR062 验证回写（2026-10-01）
已集成算法9ae583c与CR058；PPO/DQN/SAC/TD3原始bundle长度、SHA256、bundleHash及ZIP CRC通过，实际SB3 2.9.0加载通过，观察维度15。原manifest保留，schema3显式绑定发布名单版本，仅开放510300，错误资产、名单、费用、样本内日期拒绝。
接口/页面展示训练2015-01-05至2018-06-30、验证2018-07-01至2021-12-31及三折、预留测试2022至2024年；样本外下限2022-01-01，网页仍受滚动已发布行情范围约束。预热140根/最少142根。披露训练印花税0.05%与ETF回评0%的差异，不声称收益有效或跨资产泛化。

已完成：
- 离线pytest两个服务排除network：535 passed、20 skipped、16 deselected；WSL重依赖跳过项不作通过。ruff两个服务、git diff --check通过。
- node --test --test-reporter=dot apps/frontend/tests/*.test.js：95项通过。VITE_API_BASE_URL=https://43.161.223.91/api npm run build -- --base=/intelligent-quant-analysis-platform/成功，入口index-N5ivvh2a.js。
- 独立本地实际模型引擎：公开510300前复权2025-09-30至2026-09-30共242根行情，四模型均生成242净值点，DQN/PPO/SAC/TD3成交数24/52/85/88。不是云API异步验收，不证明收益有效。
- 快照数据版本27317d9657c44d9fe962e09f037758ea20dc07530078a066c463eb5b635937e9；名单33f99e5228a81019cdfad1c72ad2b896bce6cdb2d5416b5505723d73be95503b。
- Edge候选1440桌面/390手机通过，零pageerror、无横向溢出。目录为真实manifest构造的本地候选，其他接口只读公开数据，未提交线上任务；首次旧按钮选择器超时，修正脚本文案后通过。不替代线上验收。
- 证据在根目录ignored artifacts/cr062-release：local-model-load.json、real-backtests.json、verify_models.py、browser-local.json、candidate-desktop.png及candidate-mobile.png。权重、行情不入Git。

未完成：Windows/WSL默认SSH因43.161.223.91可信主机记录缺失而失败，尚未进入认证，未绕过校验或修改云端。需恢复既有SSH配置及密钥路径，不发送私钥。云候选联合验证、五模块与四模型异步任务、备份恢复、正式切换和HTTPS/Pages端到端均待完成。代码及模型需联合切换，旧镜像/模型保留回滚。分支提交供PR审核，main及Pages未验证前不称上线。未重训、采集或修改每日07:30日更。