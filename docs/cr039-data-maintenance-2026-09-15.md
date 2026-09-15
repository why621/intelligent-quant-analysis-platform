# CR-039 数据维护闭环


## CR-039 数据维护闭环（2026-09-15，开发登记）
用户确认最新 PR 合并并要求补齐“自动维护停复牌＋逐资产更新结果＋按模块判断可用性”，同时考虑常见数据源失败因素。已核实 PR23 合并提交 ae3ee2f2ee4d2bf6bd6c2f0e9926ebd2af05fffc；Algorithms/Backend/Frontend/Regression stack CI 与 Pages 工作流均 success（Regression 34934841193）。本分支 codex/data-maintenance-cr039 基于该提交。
范围与验收：① 有界获取官方停复牌信息，严格识别全天交易停牌，申赎暂停/盘中临停不得解释缺少整日日线；自动保存带来源、查询日期的事件快照，只确认已发生日期，来源异常、分页不全、结构变化保留已确认历史并显示待确认，不以缺行情推断停牌或以名单消失推断复牌。② 每只资产记录本次成功/部分/旧数据保留、实际末日与失败类别，超时、限流/拒绝、服务异常、响应格式、过期/缺日、无效价格等分别处理，保留原完整性与复权边界。③ 模块在提交前按所选资产、区间及实际基准检查数据可用性，返回同版上下文和可解释原因；用户仍可研究可用历史，缺资产不得静默删选。④ 交易事件矛盾、来源异常、复牌恢复、正常资产不受影响、模块依赖、前端竞态和契约做离线回归及本地联调；真实来源检查独立记录。
工程约束：先登记后实现，分批回写。四次自动验收预算及每次1637请求上限不扩大；停复牌请求从已有额度预留，固定超时/体积/分页上限，不无限重试、不跨源拼复权行情。官方源无法验证的交易所或业务类型明确留待确认，不伪称自动维护已覆盖。不改云数据、不重新采集行情，本批本地实现与验证；上线效果另按实际发布证据记录。

待完成：官方源适配、逐资产结果、模块预检与UI、离线与联调、最终回写。


CR039 A/B/C 实现回写（尚待验证）：已接入上交所官方 TR 全天/LXTP 交易停牌查询及每日证据保存，保留已确认历史和手工来源，缺行情不推断停牌、名单消失不推断复牌；后续实际成交识别恢复。深交所及ETF官方自动源尚未验证，明确标 pending，不宣称全市场自动维护完成。新增 assetUpdates/tradingState 与五模块 POST /data/capability，API 0.9.0，前端每模块预检和逐资产失败提示，竞态失效处理；计算端原门禁保留。格式异常不再等同于源整体宕机而连续三只阻断后续，真实传输/限流仍有界熔断。日更窗口固定365日，避免2月29日 replace(year) 异常，并匹配配置365日回看。官方查询最多1次，只使用股票已证实未消耗额度（ETF/指数135+2仍保留），总1637不变。接下来进行解析、恢复/未知状态、请求异常分类、按模块日期/基准、契约及前端回归。


## 最终核查与交付（2026-09-15，本地实现）

PR23 已合并，main=ae3ee2f2ee4d2bf6bd6c2f0e9926ebd2af05fffc。Algorithms CI 34934841182、Backend CI 34934841195、Frontend CI 34934841206、Regression stack CI 34934841193、Pages 34934841177 均 success。真实 Edge 从 GitHub Pages 访问云 API：pagesNewUi=true，健康股票相关性200、配置200，缺失ETF区间503，成功结果上下文一致。此为 CR038 合并后核验，不是 CR039 上线。

本批实现完成逐资产更新结果、故障隔离、按模块预检及前端交互；自动停复牌核验接通并验证上交所股票。自动核验尚未覆盖深交所/ETF，不把这部分标为完成。官方源异常时 pending、历史证据保留，仅当日查实全天交易停牌可新增事件；不把缺日、名单消失、盘中临停或暂停申赎当全天停牌。复牌显示由已确认停牌之后的实际成交日线建立。股票/ETF仍保持固定327资产，不静默删选。

新增实现：tools/maintain_trading_events.py（有界官方查询与证据快照）；quant_platform/data/update_results.py（失败分类）；每日构建携带 assetUpdates/eventMaintenance；读取端暴露更新结果、真实末日和 tradingState；POST /api/data/capability 及五模块前端预检，OpenAPI 0.9.0。预检只确认数据覆盖，不承诺策略参数或数值结果有效，计算端原门禁保持。全局 DailyBudgetExceeded 独立于可恢复 I/O TimeoutError，避免整轮5400秒截止被降级吞掉；固定365日回看避免2月29日年份替换错误。

### 常见数据方因素及处理

| 情况 | 当前处理和边界 |
| --- | --- |
| 超时、连接/TLS中断 | 按资产记录，保留已验证旧历史；后续计划可重试，不自动增加本轮尝试。 |
| 429限流、403拒绝、5xx服务错误 | 分别记录 rate_limited/access_denied/provider_unavailable；连续三次真实传输/源服务故障熔断该采集阶段，其他阶段继续。 |
| HTTP200但HTML、JSON/字段结构变化、SDK不兼容 | 结构/身份/来源/版本门禁；观测转换为明确失败，不让单只坏响应中断整个阶段；连续三只格式异常仍继续其他资产。SDK改变仍须适配复验。 |
| 空记录、行情延迟、末日过旧、窗口内部缺日 | 空/无效候选保留旧数据；有效但缺日允许部分发布。研究按所选区间检查，最新一条存在不代表历史完整。 |
| 重复日、非法价格、非有限数值、异常OHLC/负量 | 继续质量校验，拒绝该候选；不补价、不伪造成交或把缺数写0。 |
| 除权除息/复权因子变动 | 只使用单批完整复权序列或整段旧历史，不跨采集批次拼接价格。 |
| 停牌、复牌、盘中临停、ETF申赎暂停 | 上交所股票自动确认当日全天交易停牌；其余未核实类型待确认。后续有实际成交可恢复交易状态；未核实历史缺口仍需官方证据，不自动豁免。 |
| 新上市、退市、证券身份变化 | 沿用现有官方 pre_listing/identity_change 证据；不从空数据推断上市/退市，不自动替换固定名单。 |
| 节假日、交易日历边界、预热期不足、基准未更新 | 使用真实交易日和已发布范围。排行包括510300及90日预热，配置365日回看且需最新实价；预检说明缺失日期/样本/基准。日历超出支持年份须维护日历，不能用工作日猜测。 |
| 官方源分页不全、错误页、旧区间或异常字段 | 不使用该响应新增事件，保存 pending 诊断和既有确认记录；不把空表当复牌。 |

### 验证命令与结果

WSL 根目录，Python均使用 .venv/bin/python，工具测试设置 PYTHONPATH=.:services/algorithms/src:services/backend/src。

- `python -m pytest services/algorithms/tests services/backend/tests -m 'not network' -q -o addopts=`：323 passed，8 deselected，13.65秒。
- `python -m pytest tools/test_data_maintenance.py tools/test_collect_history_universe.py tools/test_prepare_history_batch.py tools/test_partial_publication.py tools/test_publication.py tools/test_daily_publication.py tools/test_cloud_publication.py tools/test_run_cloud_daily.py tools/test_collect_etf_candidate.py -q -o addopts=`：115 passed，82.51秒。
- `npm --workspace apps/frontend test`：63 passed；`npm --workspace apps/frontend run build`成功。合计501项离线测试通过，不将重复运行累计。
- `python -m ruff check services/algorithms/src services/backend/src`通过；本批工具按 services/algorithms/pyproject.toml 规则检查通过。git diff --check通过；CI新增维护、股票采集及观测解析测试。
- `python artifacts/cr039-data-maintenance/verify_local.py`：已保存官方响应回放，隔离去除手工601238事件后自动获得09-14全天停牌，构建真实数据候选；价格研究禁网，没有新行情请求。相关性、两种回测、健康股票配置通过；510300未更新使排行不可用，结果如实记录。
- `python artifacts/cr039-data-maintenance/check_contracts.py`：真实 status/coverage/overview 与7组模块预检响应通过Schema和同版检查；含正常股票、缺失指数基准、停牌配置与正常配置。
- Windows Node+Playwright Edge：`artifacts/cr039-data-maintenance/verify_ui.cjs`通过327目录、五预检面板、选入缺失ETF后不可用并列出510300、移除后恢复ready、实际相关性200、1440/820/390无横向溢出、无pageerror。截图留browser目录；这里报告DOM交互及几何自动检查，未声称人工逐像素审阅。
- 已合并Pages只读浏览器证据：artifacts/cr039-data-maintenance/pages-after-merge.json。无新回测任务提交到云端、无行情采集或云写入。

真实本地候选版本：0b6e7f709c40ef762ee23856912c4b201facef599f245abc2919fdc7ab0241fe。目标09-14，300股票完整（含已确认停牌），27ETF/指数沿用本地09-09基线；这是隔离回放，不冒充当前云端09-11基线。概览299有效+1停牌+0未知=300，旧指数不显示为当前值。全部真实行情、截图与任务库在忽略目录，不入库。

过程修正：精确接口清单同步新增路径；原笼统“synthetic failure”熔断夹具改为真实类别 ReadTimeout，同时新增连续坏格式后健康资产仍成功的反例；Schema测试初次语法错误修正；Ruff入口改为已安装的python -m ruff。多次自动审批因通信流中断未启动操作，只读核查后在同一授权范围重试成功，没有绕过策略或遗漏未完成执行。

### 尚未完成与下一步

1. 本分支 codex/data-maintenance-cr039 的代码、契约与文档尚未推送/合并或安装到云端；当前线上仍CR038。后续配套发布必须同时包括新maintain_trading_events工具、新读端和前端，再在云端验证官方HTTPS可达性及日更预算记录。不能只替换daily_publication.py遗漏新导入模块。
2. 深交所与ETF的自动官方停复牌来源尚未验证接入；当前明确pending，正常有行情的资产仍可用，未知缺口不误判停牌。SSE当前只确认查询当日，采集暂停期间遗留的历史缺口仍需对应历史官方证据，未实现全市场历史事件自动补齐。
3. 既有自动验收预算3/4、剩1次与09-16 07:30调度未改；未重新采集09-14、未改账本，不把本地回放或部分发布算连续两个实际交易日完整自动更新成功。MVP自动连续日验收门槛保持独立。

最终审阅补丁登记：事件 reviewed_on 应记录实际核验日期，区别于查询交易日；responseSha256 应为原响应UTF-8字节哈希。修正这两个审计字段并复验，事件覆盖规则不变。

最终审计补丁完成：reviewed_on=2026-09-15、查询交易日2026-09-14；原响应UTF-8 SHA256=c72873ba05c093a2efdd71a3aa916257120515b90c3b164e9b48ca4c4eed1ea6。42项维护回归再次通过（计入501，不重复累计）；最终候选已重新完成禁网真实数据回放、载入新进程后的7组模块预检/Schema及Edge三视口交互。上文候选版本已同步为最终0b6e7f70，旧中间候选保留在本地不可变releases中，不作为最终证据。
