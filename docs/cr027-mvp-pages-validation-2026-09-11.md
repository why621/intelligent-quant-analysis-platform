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
