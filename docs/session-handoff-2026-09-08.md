# 新会话工作交接：智能量化分析平台

## 最新：CR-014云端源验证完成（2026-09-08 19:18）

用户优先要求测试云服务器；实际在43.161.223.91后端容器测试了CR-013同六只腾讯历史，18次HTTPS全200、六只共1451条与本地逐条一致。5只242日、688981为241日（已核实停牌）。不是读取旧缓存；没有部署、更新生产数据或复测东方财富。线上仍50池、概览503。32项诊断离线/静态检查通过；[CR-014报告](cr014-cloud-history-2026-09-08.md)及artifacts/cr014-cloud-history-20260908保留证据。本轮不再重复联网；后续继续T-016f证据化停牌/上市/代码变更，再扩采。新本地诊断工具check_cloud_history.py尚未提交；原有所有修改保留。

## 优先读取：CR-013最新接续（2026-09-08）

- 下文CR-012及更早为历史。最新 [CR-013覆盖报告](cr013-history-validation-2026-09-08.md)：纯覆盖评估、版本1磁盘manifest、单只/批次硬截止、最多6只实际HTTP预算、离线重放已实现；HTTP仍0.4.0、默认50池/生产不变。
- 6只真实腾讯样本（600000/600519/688981/000001/002594/300750），2025-09-07至2026-09-07，18次请求；5只242日，688981为241日缺2025-09-08。官方公告明确该日停牌、9月9日复牌；自动分类尚未导入公告，仍gaps，不补价/不入可用缓存。
- 当前完整300分母：complete5/gaps1/not_attempted294，不是MVP完成。产物artifacts/cr013-history-20260908，零网络重放artifacts/cr013-history-replay-20260908，已执行质量笔记本artifacts/cr013-notebook/executed.ipynb；均不入库。
- Python317/前端52、Ruff/diff和笔记本通过；没有新浏览器/云端验收、推送/部署或依赖安装。HEAD仍b4634d1，所有既有及本批代码未提交。工具审批曾多次通信失败，勿误判源故障。
- 下一步T-016f：先SDD登记证据化停牌/上市/代码变更分类及研究规则，用688981已留存观察离线测试；不能简单删除市场交易日检查。再制定30—50及300只的新预算/恢复方案（当前工具故意限6只），独立指数、概览、版本一致性和运维/HTTPS仍待实现。

## 优先读取：CR-012最新接续（2026-09-08）

- 以下CR-011及更早段落均为历史快照。最新完成：真实中证300只名单（源日期2026-09-07，沪189/深111）及哈希快照，显式加载后300股票+27旧ETF，真实Flask测试客户端四页327项通过；无行情仍DATA_NOT_READY。
- Python278/前端52、静态/构建及离线质量笔记本通过；本轮没跑浏览器、没抓全量行情、没推送部署。HEAD仍b4634d1，所有原有及本轮修改均未提交，默认50池和云端保持不变。
- 先读 [CR-012报告](cr012-universe-validation-2026-09-08.md) 与四份SDD。T-016a/b/c已完成；下一批实现逐资产覆盖manifest及隔离历史采集，再独立指数/概览。不要重复下载名单或重问已确认范围。
- 本次官方名单请求2次已用完预算；留存artifacts/cr012-universe-20260908-download，后续格式复查用离线重放。已校验快照位于artifacts/cr012-universe-20260908；真实文件不入库。
- 新增jsonschema开发依赖和notebooks可选组仅安装项目.venv；笔记本已执行。生产还没有自动名单加载/日更协调配置，禁止把构造器注入测试当完成生产迁移。

> 最新接续（2026-09-08，CR-011）：用户已确认完整300只当前成分、保留ETF、固定名单最近一年并披露幸存者偏差、沪深300日频首页、团队内部教学演示。数据许可与HTTPS仍待确认。M0和CR-010已完成本地边界；本批完成M1目录分页基础（API0.4.0），解决前端50条和后台校验100条截断，未更换默认50池。Python248、前端52、浏览器13场景通过；300目录为合成测试，浏览器仅3ETF真实缓存，不是全量验收。HEAD仍b4634d1，全部修改未提交/推送/部署，临时服务已停止。先读 [CR-011报告](cr011-validation-2026-09-08.md)、[M1设计](m1-catalog-design.md) 和四份SDD；继续名单快照、独立指数及逐资产覆盖契约/实现，再隔离验证真实300数据。勿重新询问已确认范围或重做M0；下文均为历史快照。

交接日期：2026-09-08（Asia/Shanghai）；关联CR-008。本文用于恢复上下文，不替代规格、实际代码或新会话中的用户授权。云端信息是此前观测，不是本次实时检查结果。

## 续作状态（CR-009，2026-09-08）

本交接原文是CR-008历史记录；后续用户已授权本地实施。**M0/T-014已完成本地默认路径修复及三ETF真实浏览器验收**，详见 [M0报告](m0-validation-2026-09-08.md)及task最新CR-009。当前HEAD仍b4634d1，新增业务/测试/契约改动未提交；不要再按下文旧“仅文档变化”判断工作树。Python240、前端32、浏览器9场景通过；原云截图唯一根因尚无日志证明。下一步M1/T-015范围确认和逐资产覆盖契约。未推送、未部署，云端状态仍为此前历史信息。

## 1. 新会话从这里开始

用户最近要求：依据截图问题规划完整MVP、严格SDD并回写文档，然后另写本交接文件供新会话继续。上一轮已经完成规划，**T-014的业务修复尚未开始**。本轮仅做交接，不改业务、不访问云端、不提交/推送/部署。

新会话先完成以下只读启动检查，再按用户的新指令进入实现：

1. 确认打开的是本项目原工作目录，读取 [AGENTS.md](../AGENTS.md)，再完整读取 [spec.md](../spec.md)、[PRD.md](../PRD.md)、[design.md](../design.md)、[task.md](../task.md)。
2. 阅读 [MVP分阶段计划](mvp-implementation-plan.md)，重点CR-007、M0/T-014；需要部署背景时阅读 [云端验收报告](cloud-deployment-2026-09-08.md)。
3. 检查git状态、分支及差异，保留全部已有修改。若版本与本文不同，以核实后的新事实为准并补记差异，不重置仓库。
4. 开发前读取 [OpenAPI](../packages/contracts/openapi.yaml) 与本批关联Schema；先更新规格和任务状态，再小补丁实现、测试、回写。
5. 用户在新会话要求继续实现时，优先T-014。不要重新从租服务器、选数据源或整库迁移开始；没有新证据不重复已完成迁移。

## 2. 本地环境与未提交状态

- Windows目录：`\\wsl.localhost\Ubuntu\home\wangh\projects\智能量化分析平台`。
- WSL Ubuntu目录：`/home/wangh/projects/智能量化分析平台`；Windows默认终端为PowerShell，可通过wsl.exe运行Linux命令。
- 分支：`codex/regression-deployment`；本次核实HEAD：`b4634d1`（云部署记录文档）。业务提交：`a9c1b95`；此前版本：`d9f0798`。
- 本轮开始时已有未提交修改：根目录spec/PRD/design/task四文档，以及新增`docs/mvp-implementation-plan.md`。它们是上一轮工作成果，不是应清理的脏文件。
- 本轮追加：spec中CR-008、task交接记录及本文件。结束时应仍只有上述文档变化；没有新的业务代码修复或提交。
- GitHub没有收到上一轮业务发布的push；云端曾通过增量Git bundle获得提交。不可假设本地、GitHub、云源码、运行镜像、前端构建彼此完全同步，操作前分别确认。

只读启动命令（PowerShell）：

```powershell
wsl.exe -d Ubuntu bash -lc "cd /home/wangh/projects/智能量化分析平台 && git status --short && git branch --show-current && git log -3 --oneline && git diff --stat"
```

历史环境注意：WSL内此前没有rg，优先检查是否现已可用，不可用时用grep或PowerShell Select-String。Git状态以WSL Git为准，避免Windows Git产生模式/换行误判。PowerShell处理UNC路径使用Get-Content或Resolve-Path.ProviderPath，不要将带提供器前缀的路径直接交给.NET文件读取。

如工具启动失败或审批连接中断，应区分本机工具问题与远端网络故障；遵循新会话当前权限机制，不绕过审批，也不把此类失败当行情源故障。不要将本会话的临时工具二进制路径视为通用环境配置。

## 3. 已实现与已验证：不要重复、不要夸大

现有Vue/Vite/ECharts前端、Flask API、Python算法、SQLite行情与异步回测任务库；资产仍为50只股票/ETF静态混合池，不是完整沪深300。

| 工作 | 真实状态与证据边界 |
| --- | --- |
| 腾讯sz000个股成交量修复（CR-004） | 项目适配层按版本修复，带缓存规范标记；没有修改site-packages，也不是盲乘所有旧缓存 |
| 模拟配置完整性（CR-005） | 保守上海交易日截止、缺失/过期拒绝、现金权重守恒，已有测试及隔离真实数据联调 |
| 安全迁移与云后端（CR-006/T-013） | 已发布a9c1b95；5只共1335条重拉迁移，其他45只历史SQL双向差异为0 |
| 历史离线结果 | T-013记录220 passed、8 network deselected，Ruff通过，前端12项和Vite构建通过；不是本交接轮新跑的测试 |
| 云HTTP研究链路 | 历史、相关性、排行、模拟配置成功，异步回测真实后台执行成功；使用手工完整参数/明确ETF基准/固定已完成日期 |
| 尚未完成 | 页面默认路径、独立指数、完整300只、可用首页概览、日更、HTTPS/Pages浏览器、负载及完整数据恢复演练 |

本地真实源联调与单位修复证据见 [研究链路报告](research-chain-validation-2026-09-08.md)；数据源专项证据见 [沪深300源验证](hs300-source-validation-2026-09-07.md)。旧文档中“尚未部署/迁移”的段落是当时记录，后续CR-006已完成对应有限范围部署；不要据旧段落重复迁移。

## 4. 最新截图问题与精确开发入口

### A. 回测参数缺失：已确认的代码缺陷

- [use-backtest.js](../apps/frontend/src/dashboard/use-backtest.js)提交`parameters: {}`，页面缺少策略参数表单。
- [ma_cross.py](../services/algorithms/src/quant_platform/strategies/ma_cross.py)要求shortWindow、longWindow，默认5/20；[momentum_reversal.py](../services/algorithms/src/quant_platform/strategies/momentum_reversal.py)要求lookback、overboughtThreshold、oversoldThreshold，默认10/5/-5。参数应来自服务端metadata，不在各页面复制常量。
- [后端策略服务](../services/backend/src/app/services/strategies.py)提供parameterSchema；[回测服务](../services/backend/src/app/services/backtests.py)已有必填和业务校验。JSON Schema的default不会自动填补请求。
- 上轮离线调用真实validate_against_schema已重现两策略空对象的必填错误。不要删除后端required来“修复”。

### B. 相关性503：日期是重要候选原因，尚非唯一根因

- [common.js](../apps/frontend/src/dashboard/common.js)使用当前时间并toISOString，默认当天而非服务端已发布日期。
- [use-correlation.js](../apps/frontend/src/dashboard/use-correlation.js)默认ETF为510300、510500、159915；[App.vue](../apps/frontend/src/App.vue)没有向相关性/回测传递dataStatus；[use-market.js](../apps/frontend/src/dashboard/use-market.js)已经取得状态但未共享给这些表单。
- 截图请求截止2026-09-08，此前发布截止2026-09-07。provider的历史完整性检查可能因缺当天数据报上游错误；但未取得截图请求的服务端追踪，不能宣称已证明唯一原因或腾讯又坏了。
- 修复应显示已发布日期、覆盖范围、缺状态时禁用，不默默改用户已输入区间；全局latestTradeDate不能证明每只资产完整。后端也要校验，区分日期越界与真实源错误，契约同步。

### C. 隐藏的基准身份风险

- use-backtest硬编码`benchmark: '000300'`；[行情provider](../services/algorithms/src/quant_platform/data/akshare_provider.py)仍用股票代码规则，不能正确表达独立CSI300指数。
- 上次HTTP验收特意使用510300ETF，因此没覆盖页面此问题。过渡期可明确标注受支持ETF或无基准，不假称指数；正式指数在M2实现。

### D. 概览与浏览器验收缺口

- [market_fetch.py](../services/algorithms/src/quant_platform/data/market_fetch.py)仍依赖东方财富全市场列表；最后已知overview为503，无成功快照。不能把空值填0或者删除严格检查宣称完成。
- [verify_cloud_research.py](../tools/verify_cloud_research.py)使用手工正确参数和固定日期，只能证明对应API路径，不证明用户表单能运行。
- 后续必须真实浏览器点击、检查请求、等待任务并验证图表；轮询取消、重复提交、任务ID及刷新恢复也纳入M0/M4。

相关契约真实目录为`packages/contracts/schemas/`（复数），重点 [backtest.yaml](../packages/contracts/schemas/backtest.yaml)、[strategy.yaml](../packages/contracts/schemas/strategy.yaml)、[analytics.yaml](../packages/contracts/schemas/analytics.yaml)、[data.yaml](../packages/contracts/schemas/data.yaml)、[common.yaml](../packages/contracts/schemas/common.yaml)。不要误用schema/backtests.yaml。

## 5. 下一批如何执行

用户要求继续实现后，按T-014小补丁推进：

1. 核对最新差异，补真实页面请求回归用例；确认相关性在支持日期内和越界日期下的不同表现。
2. Schema驱动参数表单、默认值、策略切换与类型/边界/关系校验。
3. 共享数据状态和可用日期，前后端校验及可理解错误；有接口变更先同步契约。
4. 消除基准歧义，补忙碌/任务生命周期处理。
5. 离线测试、构建、本地真实浏览器验证分开记录；失败不勾选。每批回写四份SDD，记录命令、结果、限制和下一步。

阶段顺序：M0/T-014页面 → M1/T-015范围与契约 → M2/T-016名单/股票/指数 → M3/T-017概览 → M4/T-018五模块 → M5/T-019日更/恢复 → M6/T-020 Pages发布。详见路线文档，不另立一套冲突计划。

推荐完整300只作为最终目标、先50只验证；固定当前名单回测须披露幸存者偏差。PRD Q-01至05仍待确认：首发范围/ETF、历史名单和区间、首页统计、团队或公开展示及授权、域名HTTPS。首页改为沪深300概览是提案，不是已批准缩减全市场需求。上述决策不阻塞已有页面缺陷修复。

## 6. 验证入口与防误用

以下为WSL仓库根目录命令，不表示本轮执行过。先确认依赖存在并按改动范围选择；Python环境为`.venv`，Node版本要求见根package.json。

```bash
.venv/bin/python -m ruff check services/algorithms services/backend
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms services/backend -m 'not network'
npm run test --workspace @intelligent-quant/frontend
npm run build:frontend
git diff --check
```

迁移/源工具的离线测试可能在tools目录，不在上述services范围，改到它们需补跑对应测试。网络验证、缓存更新、HTTP异步回测不是纯离线测试：可能访问行情、写库或创建任务，先读脚本及参数并使用隔离环境。不要把固定2026-09-07复验当作未来日期下的新鲜度验收。

M5要求连续两个实际交易日自动更新，不能改时钟或连续手工运行冒充。M6要求浏览器从真实Pages经可信HTTPS调用云API，健康检查或curl不能替代。

## 7. 云端运行与恢复上下文（历史事实，操作前复核）

- 腾讯云香港轻量Ubuntu24.04，2核4GB/60GB；新公网IP为`43.161.223.91`，旧IP`43.161.219.65`已更换，不再作为连接目标。
- 登录用户ubuntu。用户此前指定本机私钥文件`D:\quantserver.pem`；仅记录位置，不读取/打印/复制私钥内容，不放仓库。新会话如无法访问该文件，按实际权限处理。
- 既有SSH known_hosts曾使用旧IP别名匹配同一实例主机密钥；连接前核对主机指纹/配置。不要关闭StrictHostKeyChecking，不自动信任不匹配密钥。
- 云项目目录`/opt/intelligent-quant-regression`，compose文件`compose.regression.yml`；后端端口127.0.0.1:8000，临时前端代理80。最终架构仍Pages前端+云后端。
- 后端业务版本a9c1b95；release标签`intelligent-quant-regression-backend:release-a9c1b95`，旧标签`intelligent-quant-regression-backend:rollback-d9f0798`。完整镜像ID见云报告；不要以latest名称推定实际运行版本。
- 云前端没有随上一批后端重建，只reload代理。新UI修复必须有相应前端构建与授权发布，不能只更新后端。
- 成功备份`/opt/intelligent-quant-backups/a9c1b95-20260908-r2`，包含代码bundle、任务库和原始/修复副本。无-r2目录是失败尝试，不能当完整备份。
- 已修5只qfq：000001、000333、000568、000725、000858，各267条（2025-08-04至2026-09-07）。无需无故重复迁移，不盲乘100。
- 上次云测试任务`56eb8d9d-13e5-4099-93cb-555410170153`已成功且未删除；资产000001、600036，ma_cross5/20，基准510300ETF，结束09-07。
- 最后记录：health200、overview503，旧状态history50只ready、overview failed、整体stale，未伪称本轮全50日更。未发现项目行情cron/timer；现在是否改变需新检查。
- 首次备份失败曾恢复旧服务；迁移成功后整库恢复演练尚未完成。不可无条件覆盖任务库丢失新增任务，不删除数据卷或备份；如需恢复先阅读云报告并获取对应授权。

## 8. 必须保留的判断与权限边界

- 东方财富TCP连通不等于行情API成功；部分日线曾成功后失败，不等于所有接口永远不可用。新浪小样本成功不等于可以立即替代全部需求。
- 腾讯历史已经有真实样本及云研究成功证据，但仍需完整300只、跨日、停牌/除权等验证。官方名单+腾讯股票历史+独立指数是推荐分工，不是全部实现完成。
- 本机VPN、云端出站、SDK语义、日期质量、UI参数是不同层面；不能把所有失败归成香港服务器或全归数据源。不再没有新证据就建议退款/换机器。
- 禁止伪造行情、混用ETF/指数、删除有效检查、将部分覆盖冒充全量。密钥、用户申请书/个人材料、真实缓存与数据库不入库。
- 本文件不授予新会话push、部署、公开发布、付费、删除或生产数据迁移权限；依当次明确请求与AGENTS.md执行。新会话最新用户指令优先。

## 9. 可复制到新会话的启动语

> 请先完整阅读docs/session-handoff-2026-09-08.md，再按其中入口读取AGENTS.md、四份SDD及MVP计划，核对当前Git差异并保留已有文档。请从M0/T-014开始实施页面参数、日期和基准修复，按小补丁推进并完成适用的离线测试与本地浏览器验证，每批回写文档。不要把旧HTTP成功当页面通过；未经我当次授权不要推送、部署或修改线上数据。需要范围确认时只阻塞相关任务。

此启动语仅为用户可选择发送的建议，不表示本次交接已开始实施。
