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
