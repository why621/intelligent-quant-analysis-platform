# CR-037：逐资产部分发布验证结果（2026-09-15）

## 需求与实施

用户要求“修改整批发布逻辑，确保能正常调用的数据能正常更新和显示”。已先在spec.md、PRD.md、design.md、task.md登记CR-037，再修改实现。本批完成本地源码、契约、测试与浏览器联调；未推送、未修改云端或重新采集行情。

- 读取器兼容严格完整的v1和逐资产校验的v2；目录保持300股+27ETF。新批次仍为带哈希的不可变快照，统一原子切换，篡改、坏价格、目录缺失继续拒绝。
- 新构建器分别验证股票、ETF和指数；健康数据正常进入新批次。单资产失败保留最近已发布版本的整段历史，不拼接不同前复权批次，不填造停牌价格。未知缺口与已核实停牌分开。
- 股票/ETF/指数阶段异常互不阻止后续阶段。ETF每个检查点有内容哈希，中途中断前已完成资产可继续验证使用。无任何有效日期推进时不发布。原四次预算、同日不重试、连续三次源失败熔断保持。
- 单次研究按选择资产和日期区间检查；未知缺口返回503，完整旧区间仍可研究。部分批次不会被记为连续两个实际交易日完整成功。
- /data/status增加availability与逐资产末日；/data/coverage增加逐资产状态；概览新增partial/unavailable，缺失不计平盘，不用旧指数冒充新值。云探针验证目录、版本、日期、涨跌计数与覆盖分母一致。
- 页面显示“发布批次目标日”、资产最后行情日期、停牌/缺口提示和部分更新状态。排行明确510300代表资产范围。OpenAPI为0.8.0，数据/策略Schema及docs/api-contract.md同步。
- Regression stack CI纳入50项发布与日更离线测试；该工作流修改已本地审查，尚未在GitHub执行。

## 验证命令与结果

环境：WSL Python 3.12虚拟环境；离线工具使用PYTHONPATH=.:services/algorithms/src:services/backend/src。

1. `python -m pytest services/algorithms/tests services/backend/tests -m 'not network' -q -o addopts=`：323 passed，8 deselected（网络测试未执行）。
2. `python -m pytest tools/test_partial_publication.py tools/test_publication.py tools/test_daily_publication.py tools/test_cloud_publication.py tools/test_run_cloud_daily.py -q -o addopts=`：48 passed。覆盖单股/ETF缺口、空数据、内部缺口、已核实停牌、哈希/坏价格/目录错误、阶段隔离、旧数据整段保留、无进展拒绝、子进程partial协议、云探针不一致拒绝和回退。
3. `python -m pytest tools/test_collect_etf_candidate.py -q -o addopts=`：2 passed；27只范围及连续三次失败熔断不变。
4. `npm test --workspace @intelligent-quant/frontend`：58 passed；含部分发布状态及重新加载失败清除旧状态。总计431项通过。
5. `npm run build --workspace @intelligent-quant/frontend`成功；`python -m ruff check services/algorithms services/backend`通过；`git diff --check`通过。
6. `python artifacts/cr037-partial-20260915/verify_local.py`：使用已有CR036股票观察和本地09-09旧完整发布，零新行情请求，构建本地v2部分批次，执行相关性、两种策略回测、配置验收通过。排行依赖510300未更新，记录不可用，未冒充全五模块成功。
7. 本地服务8768运行`tools/serve_publication_local.py`，`python artifacts/cr037-partial-20260915/check_contracts.py`：真实status、coverage、overview响应通过共享JSON Schema及外部引用检查。
8. `node tools/verify_cr037_ui.cjs artifacts/cr037-partial-20260915/browser`（Windows Node + Playwright Edge）：327目录、健康股票09-14、ETF09-09、601238停牌及09-11末日、实际股票相关性POST 200通过；1440/820/390视口检查无横向溢出、无pageerror。截图已保存。图片读取工具未能显示截图，未将自动化DOM验收描述为人工逐像素审阅。

过程问题均已记录并修复：新增测试初次导入路径错误、指数测试传参应为UTF-8 bytes；验收脚本回测需策略默认参数。Windows初次读中文文件未显式UTF-8导致写入前终止，改为显式编码重跑。自动审查曾因连接中断拒绝启动，确认无执行后按本地限定范围重试成功；不存在因此遗留的未执行验证。

## 保存真实行情的本地结果

发布版本：`7e38ede5bed6c2bd102635880649870aa99a80baf10b120f3d78f96186bed4b4`。
批次目标2026-09-14，300/327资产覆盖完整（含已核实停牌），27ETF保留09-09历史；指数保留09-09版本，仅供其覆盖区间使用，当前概览不显示该旧值。股票观察来自CR036已有09-14候选；旧ETF和指数来自本地CR024历史发布，**不是当前云端09-11版本**，本例只用于隔离故障验收。

概览：上涨116、下跌169、平盘14，priced=299；停牌1，未知不可用0；299+1+0=300。成交额等缺失指标为null。相关性、两种策略回测、正常股票模拟配置通过；旧ETF完整历史区间可读、含新增缺口区间拒绝。

证据保存于artifacts/cr037-partial-20260915/：evidence.json、contracts.json、browser/browser.json及截图；真实行情和任务数据库均留忽略目录、不入库。

## 尚未完成与上线顺序

当前云端和GitHub Pages未更新，不能声称线上已自动采用本逻辑；CR036事件配置仍待云安装。云旧镜像只认识v1，不能只上传daily_publication.py/run_cloud_daily.py就开始生成v2。

后续配套发布应先构建并安装兼容v1/v2的后端及日更运行镜像，在现有v1上回归；再同步本批日更工具（含新build_partial_publication.py、ETF检查点、验收器）、事件配置和新前端。任何切换保留既有行情指针、SQLite任务备份恢复与失败回滚流程。线上发布与Git推送按根AGENTS.md第6条“未经当次授权不推送、发布……或修改线上数据”单独执行并留证；当前仅完成用户本轮逻辑修改。

自动实际交易日验收尚未完成，现有预算仍3/4、剩1次，不重采09-14，不改失败账本，不把本地回放、部分发布或人工发布算完整自动成功日。中期展示可在配套升级后使用部分更新；是否延长日更运行需另行明确预算，不由本补丁自动扩大。
