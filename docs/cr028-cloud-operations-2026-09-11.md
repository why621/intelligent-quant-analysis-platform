# CR-028 云端日更与恢复进展（2026-09-11）

本批先登记四份SDD，完成本地实现和运维候选，尚未上传/安装/启用云调度。原Pages仍为53db3121，原自动化300-mvp仍ACTIVE、本地07:30；没有修改其prompt或启动第二个采集器。

## 已实现与验证

- tools/cloud_publication.py：合法发布ID与内容哈希校验、候选日期必须前进、在途任务阻止切换；SQLite在线一致备份→独立恢复库→integrity_check及全部逻辑记录比较；原子pointer切换、新服务探测失败回退旧pointer并重启，不覆盖任务库。
- tools/run_cloud_daily.py：固定云根目录、镜像摘要、单实例flock；候选运行容器1CPU/768MiB/128进程/只读根/无新增权限，dry-run禁网；继承既有每天一次/最多4次/1637请求/5400秒门禁。成功候选维护窗口阻止新任务，等待在途任务排空后备份/切换/验证。仅删除本次拥有的维护标记。真实scheduler来源仍需timer/journal审计，不仅凭INVOCATION_ID或trigger字符串。
- tools/verify_cloud_restore.py：真实服务读取隔离恢复库所有任务的状态/请求/结果，无worker、无外部行情请求。代码已完成，云端真实恢复演练未执行。
- deploy/mvp/quant-mvp-daily.service、timer：计划上海每日07:30，Persistent=false防止安装后立即追赶；尚未安装/启用。nginx-api.conf新增维护期间新回测503及Pages错误跨域头，尚未部署。
- 最终命令：pytest -q tools/test_cloud_publication.py tools/test_daily_publication.py tools/test_cr026_release.py，11 passed in 13.65s；Ruff四个新增Python文件通过。恢复原语改为显式关闭连接后4个核心用例亦复验通过。仅离线证据，不能认定真实云恢复成功。
- 只读云资源：内存3659MiB、可用约2573MiB，磁盘可用48095MiB；固定后端镜像sha256:d5e15f032e19f9f5343f3dac929cb37e77880b624cc4b4764d955d240345c50c。第一次无sudo Docker查询权限不足，后续严格SSH sudo只读取得镜像；未修改云端。
- 只读日更失败源：000568/000596/000617为UpstreamUnavailableError:ConnectionError；未新增采集或重试，原1/4账本不变。

## 可审阅运维包与实际阻断

artifacts/cr028-cloud-20260911/ops.tar.gz，42346字节，17文件，SHA256 e72e018d33c969f9f2bca6ec9ef206d10ae705f3dc10d987eb0795a29fbe6714。manifest.json逐文件哈希与Python tools导入闭包检查通过。内容为10个运维/采集/验证源码、2份官方名单文件、交易事件配置、原CR025失败账本以及3份nginx/systemd配置；不含密钥、个人材料或真实回测任务库。

拟上传43.161.223.91:/home/ubuntu/quant-cr028-ops.tar.gz，拟隔离安装/opt/intelligent-quant-cr026-20260910/daily-cr028。SCP实际未执行：自动审批明确拒绝，理由为内部源码、配置及失败账本向外部IP外传，要求同时明确具体载荷与目的地，未将一般MVP云部署授权认定为覆盖本包。本批不绕过拒绝，需用户明确允许该42KB包及目的地。此前本地长命令审批通信中断通过更小的明确文件清单命令解决，归档已完成；不存在prepare_cr028_ops.py（写入失败），真实归档来自显式17文件tar命令，不引用不存在工具。

## 下一步

获准后严格SHA/成员校验并安装隔离目录；保留原失败1次，只做禁网dry-run，不补跑09-10。真实备份恢复/API比对、nginx -t及维护门禁验完，再启用云timer并将旧heartbeat改为只读检查云记录，避免双重采集。成功候选云切换仍须在途任务保护及回退门禁；实际相邻两交易日及timer/journal证据齐全才能完成日更验收。公网间歇传输、许可及真实恢复保持未完成；MVP未宣称完成。


## CR-028 云端安装验收回写（2026-09-11 14:42 CST）

用户“允许继续”明确授权上述 42KB 运维包上传、安装及有界日更。此前上传阻塞已解除，最新结果如下：

- 43.161.223.91 已核验 SHA256 `e72e018d33c969f9f2bca6ec9ef206d10ae705f3dc10d987eb0795a29fbe6714`，17 个文件安装至 `/opt/intelligent-quant-cr026-20260910/daily-cr028`，固定现有后端镜像。
- `python3 -m tools.run_cloud_daily --dry-run` 在 `docker --network none` 下返回 `already_attempted`，目标 2026-09-10；账本保留失败 1 次，剩余 3 次，本轮未采集。
- `backup_restore` 实际在线备份、恢复副本及 SQLite 完整性检查通过；禁网容器 `python -m tools.verify_cloud_restore --db /restore/restored.db` 核实 18 个任务状态、请求与结果全部相同。恢复副本位于云端 `backups/install-validation`，原数据库未覆盖。
- Nginx 配置检查及 reload 成功；临时维护哨兵下 POST /api/backtests 实测返回 503 / DATA_NOT_READY，随后移除哨兵。原配置已备份。systemd 单元检查通过，仅出现已有 tat_agent PIDFile 兼容性警告。
- 原自动化 `300-mvp` 已经工具更新为只读云端验收，不再本地采集。`systemctl enable --now quant-mvp-daily.timer` 成功；下一次 2026-09-12 07:30 CST，LastTrigger 为空、service inactive、无 ExecMainStartTimestamp，未补跑今日任务。
- 云端 status/overview 门禁与严格 HTTPS 请求通过：327 资产、300 成分覆盖，当前版本 `e5f794c7094c21c2ba08903c0c5697904f0d4b0f87a3312e6285f0f4c95634fe`、数据截止 2026-09-09，仍为 stale。
- 本轮修正的是执行身份：root 隔离目录需 sudo 进入，恢复验证容器需 --user 0:0 访问恢复副本；未改包内实现。证据见 `artifacts/cr028-cloud-20260911/installed-evidence.json`。

尚未完成：连续两个实际交易日自动更新、未来真实候选的发布切换及全模块新鲜数据验收、默认浏览器网络稳定性、既有授权/许可核查。不得将定时器已启用视作两日已通过，不得标记 MVP 全部完成。后续只读核对 timer/journal、账本和发布版本，按实际结果回写；预算仍最多四次、每次最多 1637 请求/5400 秒，不得同日重试。

## CR-029 最新中期检查口径（2026-09-11）

用户确认当前为中期检查，偶发失败但重试后成功可接受，不再要求浏览器整轮零失败请求；真实完整数据、同版研究及失败保留旧批次要求不变。浏览器传输错误和日更ConnectionError均未查明唯一根因，初步排查分别估计1—2小时，深入可能需1—2天观察或更多实际运行；估计不是执行结果或承诺。浏览器有后续成功记录，09-11失败候选未重试，不能记为重试通过。

最新完成范围、成本及剩余联调见 [中期集成总结](midterm-integration-summary-2026-09-11.md)。云端18任务备份恢复/API比对已通过，不再笼统标为恢复未做；真实新批次云切换、失败回退实操、新鲜数据五模块及两相邻交易日日更仍待验。当前数据截止09-09，失败1/4、剩余3次，每次1637请求/5400秒、禁止同日重试不变。09-12/13周末不等于两交易日验收，若成功，预计09-12与09-15分别处理09-11/14行情。

本批仅文档回写，未修改业务代码、采集策略或云配置，未触发采集、推送发布。主体功能与旧批次链路已完成，不将中期容错等同全部MVP最终验收。下方或前文严格浏览器稳定性待办保留为历史证据，当前中期口径以本节为准。


## CR-028 自动验收观测（2026-09-12 11:56 CST 后，只读核查）

本次按300-mvp指令仅查询，未运行采集、补跑、重试、清账或修改云端。已读四份SDD和CR029中期容错口径。

- 云timer LastTrigger=09-12 07:30:01 CST，service同秒启动、07:58:06退出1；InvocationID `8b325b9d18cb4b29aa53b3ac68d30235` 与audit一致。timer下一次09-13 07:30，仍active。timer时间、服务时间、audit和journal交叉一致，支持本次真实自动触发；原audit.schedulerOriginVerified=false未改写。
- workerExit=0，账本目标09-11为succeeded，07:30:03至07:58:06；候选publicationId `a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a`，候选current.json一致。日志末尾300股票为289 complete、11 complete_with_exceptions、requestsKnown=900，27ETF均complete。该900仅股票请求数，不冒充全批请求总数。本轮未独立重跑完整性/五模块门禁。
- 线上发布失败根因已明确：run_cloud_daily.py第87行把含逐资产进度行及末尾结果的整个stdout交给json.loads，报JSONDecodeError: Extra data；错误发生在promotion之前。此为新增可定位的执行器输出契约缺陷，不能归为先前偶发网络失败。今天采集候选成功，不等于线上日更成功，也不能据此解释09-11那次上游连接失败的唯一根因。
- 云live指针和公网严格HTTPS /api/data/status均仍为旧 `e5f794c7094c21c2ba08903c0c5697904f0d4b0f87a3312e6285f0f4c95634fe`、截止09-09、327资产/stale。预算已使用2/4（前次候选失败、今日候选成功但部署失败），剩余2次；两日线上更新验收未完成。
- 下一步需单独登记最小输出协议修正、离线复现和有保护的现有候选发布验证；本次自动化只读范围内未实施修复或手动切换，不重新采集。优先复用现有候选，不能用候选succeeded字段掩盖线上版本未推进。Pages浏览器及新鲜数据五模块本轮未重验。

验证命令：systemctl show timer/service；journalctl -u quant-mvp-daily.service --since 2026-09-12；只读state/audit/current.json；curl --fail --silent --show-error --max-time 15 https://43.161.223.91/api/data/status。一次组合读取因审批通信中断未执行，后续缩小只读查询成功；无剩余权限阻断。此段为文档回写，不修改账本或调度。


CR-030阶段回写：本地stdout/stderr协议修复、严格解析及--promote-existing禁止采集模式完成，18项专项测试通过；云端09-11已有候选禁网五模块复验通过（300/300、十资产125样本、两策略指数回测、排行、配置100%）。上传两源码至43.161.223.91被自动审批要求具体文件+目的地授权而拒绝，未安装或切换；线上仍09-09。账本/预算不变（2/4，剩余2次），不把候选通过当发布通过。详细文件哈希、命令、两条既有Ruff告警及下一步见CR030报告。


## CR-030 授权后发布与最终回写（2026-09-12）

用户明确授权两份源码及43.161.223.91目的地，上传阻断解除。上传前一次审批通信中断未执行；核对本地哈希后重试成功。两文件云端哈希与本报告一致，旧文件已备份到daily-cr028/backups/cr030-tools后安装。

- 禁网dry-run返回already_attempted、targetDate=09-11；随后仅执行`python3 -m tools.run_cloud_daily --promote-existing`，未运行采集。发布前后state.json SHA256均为8dd9a85f809cfac4311246d356c0f2bdd2c09c8bdf6e5d1299be6e89480eb258，预算2/4、剩余2次不变。
- 云审计`daily-cr028/audit/20260912T093705Z.json`记录17:37:05—17:37:14 CST，mode=manual_existing_candidate、invocationId=null、promotion.status=promoted；候选版本a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a、截止09-11。维护标记已移除，备份及旧指针位于backups/20260912T093705Z。发布前恢复检查integrity=ok、18条任务一致。
- 线上严格HTTPS状态ready、327资产、截止09-11；发布探针已验证概览300/300同版。18个发布前任务经线上API逐个对比状态、请求、结果全部一致。第一次校验容器只读打开备份失败，改为主机只读immutable打开备份并由后端容器查询API完成验证，未改线上任务库。
- 真实Edge打开GitHub Pages，327目录正常；页面浏览器上下文通过实际CORS调用状态、概览、两策略排行、3ETF相关性及模拟配置，全部200且同一新版本，failedRequests=[]。配置basis09-11/target09-14、现金加持仓100%。证据及页面截图在artifacts/cr030-browser-20260912/evidence.json、pages.png。研究请求由浏览器fetch验证，本轮不冒称全部按钮重新操作或人工像素复核；新批次两策略指数回测已在此前禁网候选五模块复验通过，本轮未额外创建线上回测任务。
- timer仍active，下一次09-13 07:30 CST。服务早晨失败记录保留，不用清日志或reset-failed掩盖历史；本次手动发布进程成功是独立证据。

结论：解析修复已安装，已有候选发布及新版本Pages接入验证完成，旧任务保留，未重采或扩大预算。此前本报告和交接中的“未上传/未发布”已成为历史，不再索取相同授权。此次是自动采集后的人工恢复发布，不计完整自动更新成功日；连续两个实际交易日自动采集与自动发布仍待后续真实调度证明，不宣布全部MVP验收完成。真实云切换成功已验证，故障注入回退仅有既有离线证据，未额外声称完成线上故障演练。


## CR-028 09-13 周末只读自动验收观测

2026-09-13约08:55 CST核查：timer真实触发07:30:01，service 07:30:01—07:30:07 Result=success，InvocationID=2c790ec625994ca3b08c317c128645ec与audit/20260912T233001Z.json一致，journal记录正常结束。workerExit=0、decision=waiting_new_day、targetDate=2026-09-11，promotion=unchanged；尚无新交易日，未增加采集尝试。清理步骤对已自动移除的容器输出No such container，ExecStopPost按既有配置忽略该清理返回，service成功；不误记为采集失败。

state SHA256仍8dd9a85f809cfac4311246d356c0f2bdd2c09c8bdf6e5d1299be6e89480eb258，用2/4、剩余2次，自动化旧文案“剩余3次”只是迁移时基线。候选/线上指针均a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a；公开严格HTTPS状态ready/327/截止09-11，概览300/300同版，Pages HTTP200加载index-CCs2woci.js。仅复核既有候选审计和指针，未重跑完整性/五模块或浏览器交互，不将周末无更新成功算为新自动交易日。timer active，下一触发09-14 07:30；连续两实际交易日自动更新验收仍待证据。

命令：只读systemctl show、journalctl、Python读取state/audit/current.json及urllib GET公开status/overview/Pages。未运行采集、补跑、重试、清账、发布或修改云配置。本轮仅本地文档回写，不提交推送；保持监控，暂无用户动作。


## CR-028 09-14 只读自动验收观测

2026-09-14约16:41 CST核查：timer真实触发07:30:01，service 07:30:01—07:30:07 Result=success；InvocationID=ab137bebe5ca456ab870c8d208c7e534与audit/20260913T233001Z.json一致，journal正常结束。workerExit=0、waiting_new_day、targetDate=2026-09-11，promotion=unchanged。早晨尚无新的已完成交易日，不属于漏采今日收盘数据；下一次09-15 07:30调度处理新目标。既有容器清理No such container日志未影响service成功。

账本仍2次、剩余2/4，SHA256=8dd9a85f809cfac4311246d356c0f2bdd2c09c8bdf6e5d1299be6e89480eb258；候选和线上指针仍a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a。公开HTTPS状态HTTP200、ready、327、截止09-11，版本与指针相同。概览与Pages各一次GET出现TLS UNEXPECTED_EOF_WHILE_READING，未重试；本轮不能确认这两个端点及浏览器的一致性，也不能据此认定云端宕机或确定故障根因。既有09-12/13成功证据保留原日期，不替代本次未完成检查。

只读命令：systemctl show、journalctl、Python读取state/audit/current.json、urllib GET。无采集、补跑、清账、发布、预算/配置变更；未重跑候选完整性、五模块或恢复测试。timer active，两实际交易日自动更新仍待证明。结果仅回写本地六文档，不提交推送；保持既有中期偶发连接失败观察口径，无新增需用户操作事项。


## CR-028 09-15 自动更新失败只读验收

2026-09-15约10:23 CST核查：timer 07:30:01触发，service至07:56:57退出1；InvocationID=3323aeee250a4917898026ef3142680a与audit/20260914T233001Z.json、journal时间一致。本次真实自动目标09-14，workerExit=1，输出为合法JSON decision=failed，不是此前stdout解析错误复发。

具体门禁原因：2026-09-14/stocks/manifest.json记录300股票289 complete、10 complete_with_exceptions、1 gaps，900次股票HTTP请求（非全批总量）；601238缺2026-09-14，返回241/预期242交易日，末日09-11，unknownMissingSessions=[2026-09-14]，无已有事件解释。候选priceCoverageComplete=false/published=false，故未进入后续完整发布。现有证据只能认定未知行情缺口，不能断言停牌或上游连接错误，不补价、不删该股票通过验收。

账本现3/4、剩余1次，SHA256 ed004988d2d4ec191671770f04e80d040c55dec5c25f559fe4cb09f734906252；候选发布指针与线上仍a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a（09-11）。timer active，下次09-16 07:30。连续两个全自动实际交易日成功仍未达到；在当前仅剩一次尝试情况下无法凑齐两个连续全自动成功日，不静默扩大预算，预算用尽后按约定停止自动验收。

本轮公开status/overview/Pages各一次GET均TLS UNEXPECTED_EOF_WHILE_READING，未重试，公网一致性及浏览器未验证；旧批次保留以SSH读取线上指针为证据，不据本机TLS失败宣称云端服务宕机。只读systemctl/journal/state/audit/manifest/current与公开GET；未采集、补跑、发布、清账或改timer。仅本地回写，未提交推送。下一步为核实601238缺口原因及完成剩余有界观测；任何新增采集预算或修改异常分类须另按SDD处理。


09-15只读诊断补充：601238观测哈希通过，采集时间07:36:59；腾讯3次HTTP均200/error=null，SDK适配观测241行截止09-11，请求截止09-14。不是连接失败或此前JSON解析错误复发。未留存核实逐条上游响应正文，故源端/SDK遗漏与未知交易事件尚不能区分；云静态事件表无601238，官方域名搜索亦未找到可确认该日停牌证据，不自动归为停牌。etfs/index/five-module.json均未生成，股票门禁失败后未继续。云两修复源码哈希与CR030一致。

现流程：每日07:30取昨日之前最近交易日，对300股票重新获取一年窗口（非增量），完整性通过后依次27ETF、独立指数、同版五模块验证，再维护排空/备份/切换/探针；失败保留旧版。未知单股缺口阻断整批。总预算4次现已用3次，不重试同日、不扩大预算。本次仅解释；全窗重采、静态事件表、单股阻断及有界验收器均为当前工程限制，后续优化需另登记SDD，不代表已实现。结果本地回写，无采集、实现/事件/云端变更或推送。


## CR-036 完成结果（2026-09-15，本地修正）

原始公告已通过web读取巨潮PDF（2026-049）第1页：正文自09-14开市起停牌、表格起始09-15；已记录两处日期差异，只登记09-14至09-15，不预填未来10个交易日。官方链接：https://static.cninfo.com.cn/finalpage/2026-09-15/1225564444.PDF 。直接下载PDF返回403，未留存PDF或宣称PDF字节哈希；正文读取成功与下载失败分别记录。

仅修改config/trading-events.json，新增stock:SSE:601238 suspension事件，事件总数13。文件6218字节，SHA256=d16b204c88da9ac1fd4b74a3f2fdd148407770bb3517e653b24832caee564c33。没有修改生产算法、官方来源白名单或质量断言。实际241行观测哈希复验通过，缺09-14由gaps变complete_with_exceptions；额外删除09-11行的离线反例仍gaps，确认未放宽未知缺口。

云端原有300股观测及manifest只读复制到本地artifacts/cr036-suspension-20260915/seed（传输压缩2002378字节），fetch设为必抛异常并offline_reclassify=True，重分类结果289 complete/11 complete_with_exceptions、priceCoverageComplete=true、networkRequestsThisRun=0。候选ID=6cab6864615d2948177e1a4a37a7e809fc971a8fa18e67bf62d635c11b9fe936。无新采集、无修改云端失败账本或既有观测。

验证：PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python artifacts/cr036-suspension-20260915/verify.py通过；PYTHONPATH=.:services/algorithms/src:services/backend/src .venv/bin/python artifacts/cr036-suspension-20260915/verify_all.py通过（首次缺项目根目录导致导入失败，补路径后完成）；pytest services/algorithms/tests/test_trading_events.py services/algorithms/tests/test_coverage.py -q -o addopts=，29 passed/0.71s。

未完成：云端事件文件尚未安装；09-14 ETF/指数未采集、五模块和发布未执行；不能把股票离线重分类当完整恢复或自动成功日。预算仍3/4、剩1次。下一具体动作仅需将上述已验证事件配置备份安装到43.161.223.91:/opt/intelligent-quant-cr026-20260910/daily-cr028/config/trading-events.json，供既有09-16调度识别09-14/15停牌；此动作不重跑今日、不扩大预算。根AGENTS.md第6条要求当次发布/线上修改授权，本轮用户“继续”按此前诊断与本地修正执行，云安装须明确授权后做。不推送GitHub；源码修正、详细证据和文档均留本地。


## CR-038 云端上线结果（2026-09-15）

用户授权后已配套升级43.161.223.91后端、日更固定镜像/工具、事件配置和云端前端；新版本1f3a8ff2f3a1ce2bfade6ca64d689c62a35719b89c14cd57045ec8be79b67447。300股更新09-14（含已核实停牌），27ETF/指数保留线上09-11，未使用本地09-09基线，未重采。28旧回测任务备份恢复及全部线上API请求/结果逐项一致。严格HTTPS、新版云页面Edge交互/三视口及GitHub Pages实际CORS成功，健康股票相关性/配置200，缺失ETF区间503。

部署时补正人工发布后日更基线选择，6项回归通过；日更禁网预检waiting_new_day，原账本哈希ed004988d2d4ec191671770f04e80d040c55dec5c25f559fe4cb09f734906252不变，预算3/4、剩1次，下一09-16 07:30。新镜像sha256:f0b6f98637727ed5821ef0df9af035ddae61c747d0a4d7ea465f8e227c273ec0，备份/审计在/opt/intelligent-quant-cr038-20260915。

GitHub分支codex/partial-publication-cr038已推送；main要求PR且本环境无API写入凭据，尚未创建/合并PR，Pages新UI未部署（pagesNewUi=false）。云端预览https://43.161.223.91/已是新版。下一步创建并合并https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/partial-publication-cr038，再查Pages部署。人工部分发布不计两实际交易日完整自动验收。详细证据：[CR038上线报告](cr038-online-publication-2026-09-15.md)。
