后续状态（2026-10-15）：本文保留当时验收记录；当前全目录组合模型、动态排行榜及双站上线结果以[功能需求闭环](requirements-closure-2026-10-15.md)为准。

# CR066 正式多资产模型：实现与验收（2026-10-12）

用户授权正式训练、网页接入和发布，不新增付费服务。开发分支 codex/cr066-joint-model-release，原根工作区保留。云端与Pages均已上线，末尾为正式发布及实际页面验收结果，前文保留实现验证过程。

训练采用已有真实只读缓存十股票：000001、000002、000063、000100、000157、000166、000301、000333、000338、000408。未确定比赛最终名单，首批明确池内任选2–10，不声称支持全部327资产。缓存来源/原文件哈希见CR065数据准备证据。训练2025-09-09—2026-07-10（200条），验证2026-07-13—08-07（20条），测试2026-08-10—09-09（23条）；只有约一年历史、短验证与测试，测试此前已被CR065烟测使用，不属于全新盲测；资产按完整覆盖选择可能有幸存者偏差。

PPO/SAC/TD3分别种子42/137，每候选65536步、1200秒上限、48步随机回合，单线程CPU，共393216步；随机2–10子池/槽位/训练窗口。费用佣金0.03%、滑点0.02%、印花税asset_date；调仓带0.01、最小100元。依据验证收益减最大回撤选择每算法候选，先冻结全部选择再执行测试；没有按测试成绩重新训练或选种子。选中PPO137/SAC137/TD342。正式候选仍releaseEligible=false，只有绑定评估哈希的独立发布清单授权服务；smoke权重不能直接上线。

| 模型 | 测试收益 | 最大回撤 | 双边累计换手 | 显性费用/滑点（元） |
|---|---:|---:|---:|---:|
| PPO | -3.0329% | 6.2139% | 12.9886倍 | 668.47 / 250.78 |
| SAC | -3.3207% | 4.3953% | 6.0414倍 | 301.66 / 117.99 |
| TD3 | -1.7804% | 4.2090% | 4.4321倍 | 219.60 / 86.80 |

含成本等权买入持有测试收益-2.6014%、回撤3.6525%；均线目标权重基线收益-3.0420%、回撤5.8168%。该均线基线每天比较8/30均线并分配权重，不等同网页交叉事件策略。等权执行基线首日收盘后下一开盘建仓，区别于页面无成本价格基准。没有证明长期超额收益，三个策略以experimental发布。

服务新增portfolio_ppo/sac/td3；每步同时观察全组合，输出最多10槽位+现金，唯一共享账户。服务与训练共用PortfolioEpisode及broker；读取请求起点前历史进行因果预热，只展示请求样本外曲线。模拟从同一起点/资金/费用重放到最新行情日，用末日收盘生成下一开盘目标；尚未知实际成交/费用。2–10资产需共同交易日完整，停牌/未知缺口拒绝，不伪造行情。旧四单资产模型及固定510300榜保留。

OpenAPI0.12.0新增joint_portfolio模型上下文、allocationEnabled、资产数量及冻结评估；客户端允许池内子集并保持asset_date；结果增加逐资产持仓曲线、模型/基线评估及限制。用户配置改动仍不会触发自动提交。

验证证据：新增三项测试涵盖十资产服务与环境逐日账本一致/排序、smoke与篡改评估拒绝、池/成本/样本内边界；真实三模型各2/10资产共六组回测和模拟成功；前端106项通过。本地实际浏览器19项、18请求成功，1440/390/320无溢出/运行错误，手机截图已查看。真实模型本地联调用2026-09-09冻结发布及对应历史时钟，不能代替当前云验证。

命令：
- `.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -m 'not network' --disable-warnings --maxfail=3`（设置PYTHONPATH为两模块src）
- `node --test apps/frontend/tests/*.test.js`
- `python artifacts/cr066-training/run.py`；可复现入口`tools/train_joint_candidates.py --data-root <已有准备目录> --output-root <新输出目录>`，设置算法模块PYTHONPATH和已安装ML依赖。
- `python artifacts/cr066-training/verify.py`；`python artifacts/cr066-training/serve.py`；`node artifacts/cr066-training/browser.cjs`

本地失败与修复：WSL虚拟环境无Torch，使用既有WindowsTorch；Windows缺AkShare/JSONSchema/YAML安装到ignored cr066-python-deps，不升级线上依赖；UNC SQLite WAL锁不支持，联调库改为Windows临时目录。成交dataclass的fee属性不在asdict内，改为佣金+税并由账本对照覆盖。浏览器配置比较初用JSON键序误报，改深对象比较后通过。自动审批传输断开重试获准，不是安全拒绝，不绕过审批。

ignored artifacts/cr066-training包含plan/report/selection、权重与manifest/验证/测试/评估、integration.json、本地浏览器证据。权重、缓存和任务库不入Git。正式发布前需云隔离验证旧四模型、新三模型2/10资产、同参数模拟、契约/哈希与数据/日更保持，再备份切换。

最终算法/后端回归599 passed、23 skipped、16 network deselected，26.12s；前端106/106。

### CR066 云端正式发布与公网验收（2026-10-12）
功能提交2c44dbcee533ddf08778689cef2f0c7fc56c7917，分支codex/cr066-joint-model-release，PR #48已建立，功能提交四项CI均success。发布包105文件、2168276字节，SHA256 ca0a3bc1934114b1daab5acb651537320df5c921f6c95533606ec23affc14ff1。包含源码/静态前端/三个新模型，不含行情、任务库或凭据；权重未入Git。
云目录 /opt/intelligent-quant-cr066-20261012；基于CR065运行时禁网构建quant-mvp-backend:cr066，镜像sha256:2367d3bf7a6d34362f46c81fdbf2a33a31bc553a85da230a043883658b495f62。独立QUANT_PORTFOLIO_RELEASE指向镜像内只读使用的/app/portfolio_models/release.json，旧模型挂载保持。候选禁网/只读行情、隔离任务库，13回测任务全部成功（3传统+4旧AI+3新AI各2/10资产），六组新模型同参数模拟及拒绝边界通过；排行仍六项。
正式切换获取日更锁、维护排空、SQLite备份实际恢复校验，原139条任务切换前后logicalSha256均2d575c6596e89acd77b93fb36a02ce8ed5aa636992b54d9b881cff39a2c84919、integrity ok。旧模型逐文件哈希、行情发布e2add7c52b7397163c26362a1035e6af6913ad179b38775d2a7a102b4d36128e、日更两个账本及timer配置不变。日更dry-run waiting_new_day/2026-10-09，07:30timer active。备份在云目录backup，已准备回滚，本批未触发故障回滚。
云前端入口index-XTL-_R4R.js，index SHA256 11f20e7660a3cdde8c936449f21bcd4b1f7f70fea223b0df09795e9d38e90e80。真实公网Edge19项、20业务请求成功；十资产PPO共享账户回测、模拟七项配置一致、资产+现金权重和、冻结评估、1440/390/320无横向溢出/运行错误。新增真实验收任务7ae2d012-e1d3-412a-a284-182510bb2f40单独保留；不改写旧任务。
云站已完成，GitHub Pages仍待PR48合并/工作流与真实页面验收，不以云站替代。完整本地及云证据见docs/cr066-validation-2026-10-12.md和ignored artifacts/cr066-training（cloud-candidate.json、cloud-deployment.json、cloud-browser.json、cloud-job.json及截图）。未新增付费资源、未采集新行情、未重复训练旧模型。

### CR066 Pages 正式验收完成（2026-10-12）
PR #48合并提交7aa9e9836778bbd871b18ac0f6b62eafa8ea79c7，Pages工作流38230719515 success。实际 https://why621.github.io/intelligent-quant-analysis-platform/ 入口index-BmC4Uxgy.js；19项真实Edge检查、18个跨域业务请求全部成功，无运行错误，1440/390/320无横向溢出。十资产PPO联合回测及同配置模拟成功，模型范围/评估披露、资金权重和、七项配置深比较通过。
新增Pages验收任务e7989118-efe5-4e62-bebb-2d3f66290f9c，独立记录；云与Pages合计本轮新增两个真实验收任务，原139条未改写。云端与Pages均完成，不再等待功能合并。未重复训练/云切换，旧模型/日更配置保持。证据ignored artifacts/cr066-training/pages-browser.json、pages-job.json、pages-1440/390/320.png，命令node artifacts/cr066-training/browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/。
最终SDD/README/部署及交接记录推送codex/cr066-pages-evidence；该文档分支是否合并不影响已上线功能。剩余研究限制：首批训练池内2–10资产，短历史与非全新盲测，未知资产泛化及长期超额收益未证明；停牌缺口暂不支持。扩大池、长期样本和重新训练另行登记。
