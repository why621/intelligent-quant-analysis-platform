# CR042 发布权限修复


## CR042 发布权限修复（2026-09-16，登记）
用户针对自动验收发现的故障明确要求修复。目标：恢复旧发布可读/后端服务，修复root+UMask077写发布文件成0600导致非root后端无法启动的缺陷；公共发布指针和行情包明确0644，私有账本/审计/备份不扩权。严格umask下首次发布、已存在候选、失败回滚权限回归；备份安装修正工具，验证今早已存完整候选并仅发布该候选，不采集、不重试日更、不改四次账本。预算4/4耗尽后关闭既有云timer；自动化管理工具不可用情况如实记录。完整HTTPS/Pages/模块验证与数据库恢复证据独立记录，人工修复发布不计连续两实际交易日验收。逐批回写。


## CR042 本轮恢复结果与阻断（2026-09-16）
已备份到/opt/intelligent-quant-cr042-20260916，修复现网旧指针及旧发布包为0644并重启。只读复核容器healthy，HTTPS /api/health和/data/status均200，仍为旧版本1f3a8ff2（09-14股票、09-11 ETF/指数）。quant-mvp-daily.timer已disable --now，复核inactive/disabled，4次预算保持耗尽，未重新采集。
永久源码修复尚未落盘：多次exec写tools/cloud_publication.py被自动审核通信错误拒绝（stream disconnected / error decoding response body），只读证实未执行；apply_patch也因sandbox helper setup refresh错误失败。拟修正为atomic_json显式mode，公共包/指针与回滚0644，私有审计不扩权；严格umask回归待实施。今早完整5645e565候选尚未发布，不把旧服务恢复当作修复全部完成。恢复脚本与执行证据在artifacts/cr042-repair/restore.sh及.log。无推送、无新增采集、未修改日更账本。下一步待执行权限恢复后补永久修复、回归、备份安装，再发布既有候选并完成页面验收。


## CR042 继续修复完成（2026-09-16）
用户明确允许继续，前述审核阻断已解除。tools/cloud_publication.py已增加atomic_json显式mode：公共发布包、新指针及回滚指针固定0644，既有失败候选也修正0644；默认私有审计/备份权限不扩展。新增严格umask077下新包/已有0600包、成功/失败回滚四组合回归，tools/test_cloud_publication.py+tools/test_run_cloud_daily.py共25 passed，git diff --check通过。
已备份安装云端单文件源码，SHA256 61ca08d26bafc4d8a4782329890f697c28f27705be322215fb1b4f7be259e2b0；备份/opt/intelligent-quant-cr042-20260916/cloud_publication.py.before。首次部署验证脚本误从完整报告读取availability发生KeyError，未切换数据；随后改为断言provider.availability，保留原备份，禁网完整五模块验证通过后执行--promote-existing，严格umask077下发布成功。未运行采集。live=5645e56543e397380ca8a827ecb158e6c5217c28d02557c3d52bfb68f7ffce37，数据截止2026-09-15，327/327覆盖可用，指数ready，297正常比较+3确认停牌。
发布审计daily-cr028/audit/20260916T024628Z.json明确manual_existing_candidate、invocationId=null、promotion=promoted；不是自动成功日。SQLite备份恢复integrity=ok，38旧任务逐字段与线上一致；后续浏览器额外创建2个验收任务。账本SHA256 30882eed4c62071bc96d07d71cab44a26263a22eae9a7d432496ece6e7e4fd83前后不变。后端healthy，公开指针0644；云timer inactive/disabled，预算4/4不重置。
实际GitHub Pages https://why621.github.io/intelligent-quant-analysis-platform/ 严格HTTPS、Edge禁代理直连验证：327可用/09-15；511260+512010相关性242样本且页面点选计算200；排行两条；ETF配置基础09-15；均线交叉+510300基准任务fa26fa69-d2ac-41d4-8bc0-f4b962a4fe00 succeeded，动量反转+沪深300指数基准任务173ed157-0a9a-4c48-b15b-63d40556c095 succeeded，模块上下文一致。1440/390布局无溢出、无页面脚本错误。最终轮networkRetries=[]；前轮保留网络fetch失败证据及验收脚本遗漏必填parameters的400（已按策略Schema补齐），不能声称间歇网络问题已根治。
证据artifacts/cr042-repair：restore.sh.log、promote.sh.log（首次验证脚本错误）、promote_verified.sh.log、verify_preservation.sh.log、pages-bounded/pages-verification.json及截图。远程命令run_remote.py对应脚本；浏览器Node verify_pages.cjs；测试PYTHONPATH=.:services/algorithms/src:services/backend/src .venv/bin/python -m pytest tools/test_cloud_publication.py tools/test_run_cloud_daily.py -q -o addopts=。
限制：本地源码与文档尚未Git提交/推送，云补丁已安装；新行情已发布，不需更新静态页面才能取得。四次自动预算耗尽、连续两个实际交易日自动发布验收仍未达标，不恢复云timer。300-mvp本地监控因缺少automation_update能力仍无法在本任务删除，需用户管理界面停用；与已停的云采集timer区别记录。SZSE/ETF官方自动停牌源仍pending，本次完整行情不代表这些源已接入。下一步如继续长期日更需独立确认运行预算/规则，不能隐式扩大原验收次数。


## 日更能力与当前运行状态说明（2026-09-16）
用户要求回写沪深300恢复原因并确认能否每天自动更新。本次再次只读systemctl show quant-mvp-daily.timer：ActiveState=inactive、UnitFileState=disabled、NextElapseUSecRealtime为空。未修改调度或采集预算。

沪深300指数和ETF重新有数据的原因：09-16早晨真实定时采集成功取得截至09-15的327资产及指数完整候选；随后自动发布因root严格umask下公共指针0600而失败。CR042修正权限后人工发布已有候选，不是重新采集，更不是广汽集团停牌导致全部ETF永久不可用。当前线上版本5645e565，数据截至09-15，带ETF/指数基准回测和Pages五模块已通过。

必须区分：自动采集、停牌证据维护、逐资产结果、候选验证、发布/回滚代码均已实现，权限缺陷已修正；但持续每天无人值守的运行尚未启用/验收。原四次自动验收额度4/4已用完，旧timer已停，明晨不会自动执行。重新启用原timer也不能绕过代码中的预算门禁。09-16完整采集加人工补发布不能冒充连续两个实际交易日全自动更新通过。

后续若进入持续日更，需登记独立运行模式和明确运行期限/预算，保留原失败账本与四次验收记录，不清空或改写；继续保留单目标交易日去重、每次1637请求/5400秒、有界失败处理、有效资产可发布、缺数可见、备份回滚与告警。程序每天早晨07:30检查最近已完成交易日，休市或目标日期未变化不重复采集；不是每天都产生新交易日行情。必须在规则确认与对应实现验证后启用timer，并观察实际自动发布，不能仅凭配置存在称持续日更已完成。
本次仅回写本地文档，无Git推送、无调度变更。现阶段可准确表述为“自动更新功能已实现并完成权限修复；当前最新数据可用，持续自动日更尚未开启，连续两交易日自动验收未完成”。


2026-09-16完整同步入口：按用户要求将CR041前端恢复、CR042发布权限、CR043持续日更的源码/测试及中期文档汇总至新分支 codex/mvp-complete-updates-20260916。本分支包含此前尚未Git提交的6份工具和测试，前文“源码未提交/仅同步文档”是历史状态。无新增采集、云发布或运行规则变更；既有80项专项回归及前端68项测试证据沿用，不重复累计。用户合并此汇总分支即可，无需再分别合并旧CR041分支。
