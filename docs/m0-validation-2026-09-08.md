# M0 / T-014 本地实施与验收记录

日期：2026-09-08（Asia/Shanghai）；关联CR-009。代码基线b4634d1，分支codex/regression-deployment；本轮修改未提交、未推送、未部署，云端仍未取得本批代码。

## 结论与证据边界

M0页面默认路径在本地三只真实ETF样本上完成：相关性默认提交得到241个收益率样本；均线5/20、动量10/5/-5从服务端metadata进入真实表单，实际后台worker执行成功并显示242点净值曲线；显式ETF基准和刷新恢复通过。日期错误、无状态、无metadata、空相关系数、忙碌和任务生命周期有独立回归。T-014完成仅指本批M0范围；不表示完整MVP、全50只/300只、日更或公网验收完成。

原截图相关性503的服务端日志未取得，不能将日期越界认定为其唯一根因。本轮证明的是修复前页面日期与已发布日期不符，以及修复后本地合法/越界/真实源错误走不同分支。

## 实际修改

- 前端新增useResearchDates和useStrategyParameters：发布日期初始化、2025—2026日历边界、用户编辑保护；参数默认值/必填/类型/有限性/边界/关系统一来自metadata。空metadata不能提交。
- 两策略Schema增加x-relations；服务端保留required及策略业务校验，并拒绝NaN/Infinity参数。
- 相关性计算及回测入队前调用ResearchDateGuard。400 DATE_OUT_OF_RANGE含请求日期、可用范围及symbols；503 DATA_NOT_READY表示缺发布状态；范围内真实源错误保持503 UPSTREAM_UNAVAILABLE。全局截止不是逐资产覆盖证明，provider完整性校验未移除。
- 默认无基准，只有成功加载目录中的active ETF可选，后端同步拒绝000300独立指数/股票/未知基准；结果明确ETF身份或Alpha/Beta不适用。
- BacktestJob新增request原始请求快照，无表结构迁移。最近任务ID保存在按API地址区分的本地存储，支持手动恢复查询；旧结果显示原任务策略、日期、参数和基准。防重复提交、有界轮询、失败/超时保留ID、组件卸载忽略晚到结果均已验证。
- 图表：null相关系数留空并提示；策略资金与基准净值按各自首日归一为1后比较，显示口径，不改变原始API数值或指标；热力图底部留白避免色条遮挡资产标签。
- OpenAPI 0.3.0、strategy/data/backtest/common Schema与docs/api-contract.md同步。保留原四份SDD和两个未提交交接/规划文档，追加当前进展。

## 本轮运行的验证

| 层级 | 实际命令 / 工具 | 结果 |
| --- | --- | --- |
| 修复前回归 | npm run test --workspace @intelligent-quant/frontend | 12通过、2失败；两页面实际默认09-08而非状态09-07 |
| Python离线 | 见下方完整命令 | 240 passed、8 deselected，14.45秒 |
| 前端离线 | npm run test --workspace @intelligent-quant/frontend | 32 passed |
| 静态检查 | .venv/bin/python -m ruff check services/algorithms services/backend tools/serve_m0_local.py | 通过 |
| 前端构建 | npm run build:frontend | 通过；最终主包index-FBkA7UZc.js |
| 差异 | WSL git diff --check | 通过 |
| 外部源样本 | tools/serve_m0_local.py --prepare | 3只ETF各242条，完整日期/缓存校验通过 |
| 本地浏览器 | tools/verify_m0_browser.cjs，Edge 152.0.4191.66 | 9个场景通过，pageErrors为空；实际表单POST、worker、SVG图表与截图 |
| 云端 / 发布 | 未执行 | 不沿用旧授权 |

WSL仓库根目录Python完整离线命令：

```bash
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms services/backend tools/test_check_hs300_sources.py tools/test_repair_volume_cache.py -m 'not network' -o addopts= -q
```

32项前端用例包含原12项、新20项：服务端默认值变化、策略切换/关系/有限性、缺状态与晚到日期、用户日期保护、非法/重复资产、ETF身份、防重复点击、轮询超时恢复、存储恢复、卸载晚响应、不存在任务、null矩阵与净值单位比较。轮询超时使用测试时钟，不用于日更验收。

## 真实样本与浏览器任务

本地data/processed/market_data.db原有OHLCV为0行、无发布截止；因此未用空库冒充真实数据。新建忽略目录artifacts/m0-20260908，从腾讯历史接口依次拉取510300、510500、159915。请求2025-09-07至2026-09-07，实际交易日2025-09-08至2026-09-07，各242行，共726行，qfq。只有全部样本经provider完整性和存储校验后才写隔离样本状态；状态明确“3只ETF、不是全量日更”。

本地服务仅绑定127.0.0.1:8765，资产目录限制为上述3只，单独backtests.db，实际Flask后台worker；服务阶段禁止再次请求上游。浏览器直接使用已构建页面，同源访问API。概览无快照仍503，未生成假概览或将其称为通过。验收结束已停止临时服务，保留忽略目录证据。

| 页面场景 | 最终任务ID | 净值点 | 状态 |
| --- | --- | --- | --- |
| ma_cross default | cea62ecd-fa90-44e7-a259-5febfec609ce | 242 | succeeded |
| momentum_reversal default | 659f6726-865f-48bc-93b4-08a82435255d | 242 | succeeded |
| ma_cross ETF | 4a0ce0d4-0818-42e9-8548-b708c9d8a76c | 242 | succeeded |

两策略默认无基准时Alpha/Beta均为null；显式510500ETF时返回基准指标。上述收益数值仅为实现回归结果，不用于评价策略投资价值。

浏览器同时验证：默认三ETF相关性热力图；两策略真实参数表单；明确ETF比较；刷新后用保存的任务ID恢复原策略结果，POST数不增加；非法关系/越界日期按钮禁用。缺状态、缺metadata和nullable矩阵共3项是**浏览器故障注入**，仅证明错误体验，不是行情源可用性证据。重复点击/轮询超时/卸载并发边界由离线composable用例覆盖。

本机保留的原始验收输出不入Git，重新运行工具可生成：

- [样本日期与行数](../artifacts/m0-20260908/sample-evidence.json)
- [浏览器请求与任务摘要](../artifacts/m0-browser/evidence.json)
- [相关矩阵截图](../artifacts/m0-browser/correlation.png)
- [均线无基准截图](../artifacts/m0-browser/ma_cross.png)
- [动量无基准截图](../artifacts/m0-browser/momentum_reversal.png)
- [ETF比较截图](../artifacts/m0-browser/ma_cross-etf.png)

复现：先构建前端，在新目录运行prepare（拒绝覆盖已有目录），再启动本地服务；Windows使用已有Playwright模块与Edge运行浏览器工具。NODE_PATH由当前运行时实际路径提供，不在脚本里硬编码机器路径。

```bash
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/serve_m0_local.py --prepare --data-dir artifacts/m0-new-run
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/serve_m0_local.py --data-dir artifacts/m0-new-run --port 8765
node tools/verify_m0_browser.cjs http://127.0.0.1:8765 artifacts/m0-browser
```

## 失败记录与未完成项

- 默认文件执行和图片工具因Windows沙箱setup refresh错误无法启动；改用经过自动审批的明确本地命令。审批偶发stream disconnected，核实未执行后重试成功；不是行情或云网络故障。
- 一次Python测试命令遗漏PYTHONPATH导致5项收集错误，修正后完整离线通过。两处业务/策略格式与一处验收脚本导入排序由Ruff指出，修复后通过。
- 浏览器前两次因嵌套label定位器、误查canvas（实际SVGRenderer）失败，修正脚本后重跑；不将前两次记为通过。实际截图审阅发现净值单位差异和热力图标签重叠，已修复并最终复验。
- 未获取原截图云请求日志；未做云端回归、推送、部署、线上迁移或全量刷新。
- M1仍需确认Q-01至04并设计逐资产可用区间/名单版本；M2独立指数和完整范围、M3概览、M4其余五模块一致性、M5真实跨交易日日更与恢复、M6 HTTPS/Pages均未完成。
- 页面保存最近任务编号并支持恢复查询；创建请求若已到达服务器但响应在网络中丢失，客户端可能拿不到编号，跨请求幂等键/任务列表属于后续任务可靠性工作。
- 本批需要前后端协调发布才能在云页面生效；当前未获发布授权。回滚仅撤销本批实现与契约，不删除任何缓存、任务或备份。

最终文档/工作区检查：WSL Python只读检查9份Markdown、89个本地链接、UTF-8及代码块配对均通过；git diff --check通过；HEAD仍b4634d1、暂存区未变，3个行情/任务/浏览器运行产物路径由artifacts规则忽略；127.0.0.1:8765已关闭。最终热力图与ETF净值截图已人工审阅，资产标签、色条和首日=1比较正常。