# 当前状态：CR062已正式上线（2026-10-01）

PR42已合并，云端与Pages真实验收通过；下文早期“未上线/SSH阻塞”记录已被末尾正式上线验收取代。四模型仍为实验性且仅开放510300；保留429跨域错误提示问题。

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

### CR062 云上线续批登记（2026-10-01）
用户确认PR42合并并要求沿用既有连接继续发布。已从旧交接157/312行恢复D:\quantserver.pem和HostKeyAlias=43.161.219.65，严格主机校验成功；此前连接阻塞解除。云基线镜像cr057 sha256:4a1f05bea8712d9b32fa227beda8710cb59ecba9be77cf52337349c6f029f1c0，SB3 2.9.0/torch2.14.0+cpu；合并main 7f20f6f。先禁网只读行情候选验证，再任务排空/实际备份恢复、代码与四模型联合切换，失败回滚；保持07:30日更和账本。结果后续逐项回写。


## CR062 正式上线验收（2026-10-01，已完成）
PR42合并main `7f20f6fbc940fffa6c107dad11e78f47fb77a397`。Backend/Frontend/Algorithms/Regression及Pages五个工作流均success；Pages发布run 36817311611，线上入口index-N5ivvh2a.js与本地生产构建一致。
- 使用文档记录的D:\quantserver.pem及HostKeyAlias=43.161.219.65严格验证登录43.161.223.91，未更改可信主机记录、未输出私钥。此前“连接缺失”是未找到已有配置，现已解除。
- 包108文件/9,043,139字节，SHA256 e05476ee305f31a5b90fa07259a460b292041e7606809ce98203d34c61c35eb4，两端及成员哈希通过。仅源码、页面、四个原始模型与发布配置；无凭据、行情库、任务库。
- 云镜像quant-mvp-backend:cr062，sha256:8525f9ee9cbfe8ebc711db8a6c5e5b25467b0dce00e0711ad2893af45ca447bf。发布目录/opt/intelligent-quant-cr062-20261001；模型挂载该目录/models只读，保留旧cr057镜像和cr049模型。
- 云端禁网、只读行情、同线上quant UID999、独立临时任务库：五模块通过，ma_cross/momentum_reversal/PPO/DQN/SAC/TD3六个异步任务均succeeded，排行6项；错误资产/模型/日期被拒绝。首次验收脚本漏传统策略必填参数，以及第二次输出目录权限错误，均仅发生在隔离候选；修正脚本后完整重验通过。
- 切换取得runner.lock、开启维护、排空任务，SQLite实际备份并恢复验证。前后原有113行，integrity=ok，逻辑摘要均bd3ac9e55e0a1f12e64ce6daa71be78e83a4d575e0ea8f72bbb8da1197da210a。备份在/opt/intelligent-quant-cr062-20261001/backup，含compose/image-id/原源码/原前端/任务库恢复副本。代码及模型联合切换，容器healthy、nginx配置检查通过；回滚分支已准备，本次成功切换未触发故障回滚，不声称完成新版本故障回滚演练。
- 行情指针维持27317d9657c44d9fe962e09f037758ea20dc07530078a066c463eb5b635937e9；旧验收及持续日更两份state摘要不变。禁网daily dry-run=waiting_new_day、targetDate=2026-09-30、mode=continuous。timer active，下一次2026-10-02 07:30 CST，未采集、补跑、重训或重置账本。未来日更成功仍以届时运行证据为准。
- 真实GitHub Pages -> HTTPS浏览器验收：概览/相关性/策略回测/排行/模拟配置均通过，同一数据版本；四新模型均succeeded，费用stampDutyPct=0，原bundleHash一致。桌面1440/手机390无横向溢出、零pageerror；训练2015—2018、验证2018—2021及三折、预留测试2022—2024、样本外下限/当前可用区间/140根预热/正确TD3文案通过。

### 公网验收限制与保留问题
首次快速连发触发既有jobs限流429；另一轮首页初始化与探测叠加触发api限流429。网关日志有明确证据，非模型或数据执行失败。429未带CORS头，浏览器将其显示为Failed to fetch；未在本批静默放宽安全限流，错误提示改进留待后续补丁。本地脚本一次UTF-8读取失败后误执行旧脚本，额外产生了三个验收任务，均保留未删除；随后改为明确恢复查询，遵守间隔。最终一轮恢复前三任务并提交TD3、五模块验收通过，零传输重试。不要将此写成“网络从未失败”。

### 线上任务证据
- ppo：`e37d15f6-bca7-4408-9586-98c59ec3bd9f`，succeeded，模型`ppo-510300-s42`。
- dqn：`d5861625-9a77-422a-accd-6b279df414e5`，succeeded，模型`dqn-510300-s42`。
- sac：`2b5d52c8-c449-4711-9e34-e42e09f155bb`，succeeded，模型`sac-510300-s43`。
- td3：`1248c656-72fa-4bb9-8928-0611eb60a9e1`，succeeded，模型`td3-510300-s44`。

完整本地证据：ignored artifacts/cr062-release/online-browser.json、online-desktop.png、online-mobile.png及部署脚本；云端validation.json/deployment.json。线上地址 https://why621.github.io/intelligent-quant-analysis-platform/ 。
