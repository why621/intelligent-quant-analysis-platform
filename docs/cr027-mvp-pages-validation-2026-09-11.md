# CR-027 MVP功能审计与Pages发布准备（2026-09-11）

本轮用户授权检查MVP并部署云后端+GitHub Pages前端。五模块已有实现，MVP整体仍未验收；新Pages候选尚未发布。下述新验证与历史证据分开记录。

## REQ验收矩阵

|需求|实现与现有证据|剩余门槛|
|---|---|---|
|01 资产池|当前官方300股票+27ETF，分页/身份/版本；CR024本地完整验收，本轮云状态327、本地浏览器327选项|Pages同池实际浏览器待验|
|02 日线质量|一年OHLCV、单位、停牌/上市事件、完整性门禁及不可变发布已实现|09-10新候选失败，云仍09-09；连续更新不通过|
|03 指数|独立CSI:000300价格指数和同期回测已实现，CR020/024证据|Pages指数回测待验|
|04 概览|同版本300成分宽度/成交额/指数；本轮本地浏览器300/300|Pages真实跨域待验|
|05 相关性|2—10资产、共同收盘区间、空值及版本校验；CR024十资产，本轮正常/图表故障两场景真实API200|Pages十资产待验|
|06 回测|两传统策略、参数、异步持久化、指数/无基准、恢复；CR024本地/CR026云HTTP证据|Pages按钮/刷新恢复待验|
|07 排行|同版本区间与成本、两策略排行已实现|Pages跨域待验|
|08 模拟配置|权重/现金守恒与过期拒绝已实现；CR024/02609-10验收|当前快照过期，不宣称最新配置可用|
|09 失败恢复|缺失不造零、失败保留旧发布、版本冲突；本轮修复图表失败阻塞API启动|完整灾备切换未演练|
|10 公网运维|云服务已部署；本轮云本机可信TLS、Pages CORS、续期定时器通过|公网443超时、Pages未更新、两日日更未通过、完整备份恢复/许可尚缺|

## 本轮修正与验证

- App.vue图表与数据独立初始化；三图表各自捕获加载失败，展示错误，迟到图表使用当前结果，卸载后不创建实例。新增startup.js与3个回归测试。
- Pages工作流默认API为https://43.161.223.91/api，保留变量覆盖与原HTTPS校验，不把真实行情写入前端产物或Git。
- `npm test --workspace @intelligent-quant/frontend`：57通过。
- `VITE_API_BASE_URL=https://43.161.223.91/api npm run build --workspace @intelligent-quant/frontend -- --base /intelligent-quant-analysis-platform/ --outDir ../../artifacts/cr027-pages-20260911/dist`：通过，独立候选及manifest已保留，尚未上传。
- 同源本地构建通过；`tools/serve_publication_local.py --publication artifacts/cr024-publication-20260910 --jobs artifacts/cr027-local-20260911/backtests.db --port 8767`启动隔离服务。
- `tools/verify_cr027_startup.cjs`使用真实Edge和真实327只读快照，两场景均通过：正常加载、明确注入图表请求失败。327目录、300/300概览、相关性200及完整发布标识，pageErrors=[]。截图及startup-evidence.json位于artifacts/cr027-local-20260911；不是公网验收。
- 云SSH只读检查：curl保留43.161.223.91身份、连接127.0.0.1验证可信TLS，状态327/09-09/stale，版本e5f794c7094c21c2ba08903c0c5697904f0d4b0f87a3312e6285f0f4c95634fe。OPTIONS精确允许https://why621.github.io，包含Content-Type和X-Research-Version。证书timer active，service Result=success/ExecMainStatus=0。
- 公网HTTPS curl连接8秒超时，未完成握手；需腾讯云放行入站TCP443，已请用户操作。
- 首次Git只读探测用了默认身份，publickey失败；随后读取core.sshCommand，使用仓库专用id_ed25519_github及严格主机校验成功查询origin main/HEAD=8a8973a8d142884ed56715549606eb62e3457703。无需用户重配Git身份；该成功只证明读权限，推送尚未执行。
- 本轮全量Python回归及git diff --check因自动审批服务连接中断未执行成功，不计通过。历史375通过/8网络排除属于CR024。

## CR025真实失败账本核对

state.json记录09-11 10:17:49.196581至10:29:25.553483（+08:00），目标09-10，failed/stock candidate incomplete。manifest：194 complete、7 complete_with_exceptions、3 source_error、96 not_attempted，300分母保留；606实际HTTP，预留1020，计费采集秒474.957116133，priceCoverageComplete=false、published=false。未重试失败日、未降低检查、未推进ETF/指数或切云包。已使用1/4尝试，无连续成功两日；trigger字段不单独当调度来源审计证明。

## 下一步

放行公网443后严格验证外部TLS/CORS；补验补丁检查后将审阅过的源码/前端发布至既有GitHub Pages，禁止行情、数据库或密钥入Git。随后真实Pages浏览器五模块、过期边界、刷新恢复及截图验收。保持旧云包可回退，不把页面200当作数据链路闭环。继续原有有界日更安排，不自动重试失败日，不将本地新包自动部署云端。数据更新闭环与完整恢复、许可各自保持未完成。


CR-027最终补验：审批通信恢复后git diff --check通过，完整Python离线377 passed/8 deselected（39.86s），2条既有network标记未注册警告；前端57通过及两浏览器场景不变。本地验证服务已停止。此前审批中断记录保留为历史，已不再阻塞本批验证；Pages候选未发布，当前等待公网TCP443放行，未认定Pages数据闭环或MVP完成。


CR-027发布续作（2026-09-11）：用户已放行443并要求继续，公网curl严格证书验证成功，/api/data/status返回327/09-09/stale及既有e5f794c7094c版本。解除TLS连接阻塞，继续已授权的源码推送与GitHub Pages发布。保留过期快照边界，不将新页面发布当作日更完成。


CR-027公网与GitHub续作结果：用户放行443后，公网严格HTTPS读取327状态成功。源码/文档提交804387c已生成；直接推送main被GitHub GH013拒绝（Changes must be made through a pull request），未更改main。随后成功推送codex/mvp-pages-cr027分支。标准环境无GitHub API token，已配置Git凭据助手也未返回HTTPS凭据，因此未创建PR；创建入口https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/mvp-pages-cr027，已请用户按规则创建/合并。Pages尚未重新构建，不以分支上传冒充Pages发布。公网完整浏览器补验脚本准备命令因自动审批通信断开未执行，仍待验证；本轮公网证据限可信TLS与327状态，历史CORS及本地浏览器证据分别保留。


## CR-027 Pages实际发布与验收（2026-09-11，合并后）

用户已合并PR #20。GitHub main合并版本53db31211ff21387e6dccd303ae19d652bd74dd4；Pages工作流34559932354于03:50:07至03:50:34 UTC完成，conclusion=success。实际网页引用index-y1fijrdp.js/index-CayoFdRP.css，与已验Pages候选一致。[正式Pages入口](https://why621.github.io/intelligent-quant-analysis-platform/)，云API为https://43.161.223.91/api。解除旧“Pages未发布/等待PR/443”的当前阻塞，保留历史记录。

真实Edge直接打开GitHub Pages，无成功响应注入、无忽略证书校验：完整327选项、300/300概览、两策略排行通过浏览器跨域读取；10股票600000/600009/600010/600011/600015/600016/600018/600019/600023/600025的10x10相关性返回242共同区间样本，45对关系，统一e5f794c7094c发布版本。两策略由页面提交并绘图：ma_cross任务745da643-ff3d-475a-8633-44260aa24887、momentum_reversal任务6c66e3cc-1445-4329-a1ff-f7f802c9e8f3。后续实际恢复查询确认两者succeeded及同一数据上下文。

刷新后点击既有“恢复查询”恢复结果，新增回测POST=0。模拟配置按钮真实返回503 DATA_STALE并显示错误；云快照09-09已过期，不能据此称最新配置成功或日更完成。1440/820/390屏宽均无文档横向溢出，锚点未被页头覆盖。

验证过程有保留的失败：第一轮过早检查尚未加载完的目录；修正等待327选项而未降低断言。第二轮相关性POST出现ERR_EMPTY_RESPONSE，云日志只有成功OPTIONS、没有对应POST；独立curl真实HTTPS三ETF127样本成功，后续浏览器十股票也成功。第三轮脚本误把刷新当自动恢复，补上产品已有的显式恢复按钮；复用两现有任务，没有重新创建。默认网络恢复曾ERR_EMPTY_RESPONSE；后端IP直连对照完成恢复/503/三屏检查，但首次目录请求ERR_CONNECTION_CLOSED，因此整个严格无失败请求断言仍未通过。没有证明唯一网络根因，不把直连对照当默认网络稳定通过。读取本机代理设置的命令因审批通信中断未执行，不推定本机代理配置。

证据：artifacts/cr027-pages-20260911/deployment.json及browser下attempt-1-startup-race.json、attempt-2-transport.json、attempt-3-recovery-step.json、recovery-attempt-1-transport.json、recovery-evidence.json和截图。tools/verify_cr027_pages.cjs与tools/verify_cr027_pages_recovery.cjs保留可复验步骤。截图已生成、DOM/几何校验通过，但本机图片查看工具失败，未额外声称人工像素级视觉复核通过。

结论：Pages新版已发布，前端Pages→HTTPS云后端→真实327快照研究链路已实际运行；不能称全场景稳定性或MVP全验收通过。剩余为间歇传输故障、当前数据过期及连续两个实际交易日自动更新、完整恢复演练和许可。四份SDD及交接回写在本地工作区，合并后未再修改产品或发布新版本。

## CR-029 最新中期检查口径（2026-09-11）

用户确认当前为中期检查，偶发失败但重试后成功可接受，不再要求浏览器整轮零失败请求；真实完整数据、同版研究及失败保留旧批次要求不变。浏览器传输错误和日更ConnectionError均未查明唯一根因，初步排查分别估计1—2小时，深入可能需1—2天观察或更多实际运行；估计不是执行结果或承诺。浏览器有后续成功记录，09-11失败候选未重试，不能记为重试通过。

最新完成范围、成本及剩余联调见 [中期集成总结](midterm-integration-summary-2026-09-11.md)。云端18任务备份恢复/API比对已通过，不再笼统标为恢复未做；真实新批次云切换、失败回退实操、新鲜数据五模块及两相邻交易日日更仍待验。当前数据截止09-09，失败1/4、剩余3次，每次1637请求/5400秒、禁止同日重试不变。09-12/13周末不等于两交易日验收，若成功，预计09-12与09-15分别处理09-11/14行情。

本批仅文档回写，未修改业务代码、采集策略或云配置，未触发采集、推送发布。主体功能与旧批次链路已完成，不将中期容错等同全部MVP最终验收。下方或前文严格浏览器稳定性待办保留为历史证据，当前中期口径以本节为准。
