# CR067 日更故障调查与恢复

2026-10-14 完成云端修复和人工恢复。每日北京时间 07:30 调度保留；下次自动执行是 2026-10-15 07:30，其成功结果尚未观察。本次手动恢复不计为自动连续成功日。

## 原因与证据

- 10月13日、14日的定时任务正常启动，在约07:58采集结束后失败，目标日分别为10月12日、13日。持久化账本均为 `RLDependenciesMissing: joint inference requires optional [rl] dependencies`。
- CR066服务镜像设置了 `QUANT_PORTFOLIO_RELEASE=/app/portfolio_models/release.json`。日更复用此镜像，但其 `PYTHONPATH=/app/code:/work` 不含服务推理依赖。数据校验的 `create_app(TESTING=True)` 仍继承模型环境变量，构建策略目录时误加载联合模型。
- 同一镜像、禁网容器中复现原始异常，调用链为 `verify → create_app → StrategyCatalogService → JointPortfolioStrategy → load_portfolio_bundle`。修复后在同一环境通过候选校验，确认是环境配置耦合，而非定时器未运行。
- CR066发布时只验证了日更 `dry-run waiting_new_day`，未执行采集后的数据校验，因此漏检了这条路径。此次补充两条校验分支的环境污染测试和真实云镜像禁网验证。

## 修复及恢复过程

1. `run_cloud_daily.runtime` 显式清空两个模型发布环境变量；`verify_published_provider.publication_app` 通过应用配置显式设置旧RL、新组合模型发布配置为 `None`。数据门禁继续检查传统策略的五个模块；服务端模型配置、加载校验和能力不变。
2. 新增 `recover_daily_publication`，仅允许连续账本最新一次指定日期的模型依赖错误恢复。验证已保存股票/ETF清单哈希与区间，从原观察记录及事件构建候选，完成数据门禁后发布候选。原失败记录不变，另追加 `manual/offline_recovery/requestUpperBound=0`，不重置当日采集限制。
3. 在独立目录、原行情只读、`--network none` 容器中验证，再获取日更锁，备份工具、账本和指针，安装补丁。生产恢复亦禁网；维护期间排空任务、SQLite一致性备份并实际恢复校验后切换数据。12:44第一阶段恢复至10月13日，326/327可用。
4. 唯一缺口为601059的10月12日：停牌证据存在于失败日文件，但未进入10月9日已发布基线，故次日未继承。旧维护程序保存了事件和响应哈希，没有保存响应原文。为重新核验，做了**一次**人工、无重试的上交所历史停牌查询，保存原文；新响应SHA256与10月13日采集时的记录完全一致：`fb6dde5c72b96262419b2299ab7596ecad31975badad0ef7000fbce0e3e49151`。
5. 仅恢复官方确认的601059在10月12日全天停牌事件。重新构建后，所有资产的全部价格记录、指数原文均与第一阶段版本逐项相同；完整五模块禁网门禁通过。12:50完成备份、维护锁、同日元数据修正与回滚保护下的指针切换。该人工事件修正独立审计，不放宽正常 `promote` 的交易日必须推进规则。

没有整批重采、重训、重建服务镜像或部署前端。修复上传初次被自动审批拒绝，用户随后明确授权上传文件至43.161.223.91并完成修复，阻断已解除。

## 最终验证

| 检查 | 结果 |
|---|---|
| 公网 `/api/data/status` | `ready`，latestTradeDate=2026-10-13，readyCount=327、affectedCount=0 |
| 市场概况 | 日期10月13日；300股中299只有当日价格、1只已核实停牌、未知缺失0 |
| 排行 | 6项，区间2026-09-14至2026-10-13，无unavailableStrategies |
| 模型目录 | 2传统+4旧单资产+3联合模型；模型哈希不变 |
| 联合模型公网模拟 | PPO/SAC/TD3分别十资产成功，资产与现金权重和均100%，同一10月13日版本 |
| 历史任务 | 142条，备份及实际恢复integrity=ok，切换前后逻辑SHA256一致 |
| 账本 | 两条自动失败保留；追加人工零采集恢复及一次官方事件核验记录；旧验收账本未改 |
| 调度 | timer active，配置不变；下一次2026-10-15 07:30 CST |

最终数据版本：`91566be922b0488cba900a608dd8879e06a8f7d0c5896954639d357af9e636b5`。
142条任务逻辑SHA256：`883f4340aabfcef5fb505f1c3109ed9faeb9ae5e785cb8e39bb2df4edbaa75e3`。

本地验证命令（工作树内，PYTHONPATH为 `services/backend/src:services/algorithms/src:.`）：

```sh
python -m pytest tools/test_daily_recovery.py tools/test_daily_publication.py tools/test_run_cloud_daily.py tools/test_cloud_publication.py tools/test_partial_publication.py -q
python -m pytest tools/test_daily_recovery.py -q
python -m ruff check tools/recover_daily_publication.py tools/test_daily_recovery.py tools/verify_published_provider.py
python -m compileall -q tools/recover_daily_publication.py tools/verify_published_provider.py tools/run_cloud_daily.py tools/test_daily_recovery.py
git diff --check
```

第一次测试64通过、1失败，失败为新增测试夹具扩大股票窗口却未保留旧指数窗口；修正夹具后7项新增测试全部通过，原58项回归已通过，共65个不同测试验证通过。Ruff修正导入排版后通过；编译、差异检查通过。排版后的云端恢复脚本以AST相等检查同步，未改变行为。

## 证据与后续

- 云端 `/opt/intelligent-quant-cr067-20261014`：原异常、隔离候选、部署审计、工具与账本备份；`event-correction` 包含重新取得的官方响应、完整五模块结果、事件修正和第二次任务库备份。
- 日更审计：`daily-cr028/audit/cr067-offline-recovery.json`、`cr067-event-restoration.json`。
- 本地 ignored `artifacts/cr067-daily-repair`：恢复脚本、deployment.json、event-deployment.json、public-api.json、portfolio-simulation.json。行情、数据库、响应原文和密钥不入Git。
- API/OpenAPI和网页无需变化。源码与SDD保留在 `codex/cr067-daily-repair`；已按后续用户授权推送GitHub功能分支，尚未合并main；云端修复已生效。
- 后续检查下一次07:30真实自动执行及账本/线上日期，不用本次手动运行代替。以后恢复跨多个失败日时，应同时检查失败日事件证据是否继承；不能只看价格截止日。SZSE/ETF官方事件自动源仍为既有pending边界，不等于本次327资产仍有未知缺口。

### CR067 GitHub 推送（2026-10-14）
用户本轮明确要求推送相关更新。修复提交94ab5dc及此前CR066最终验收文档c878cf0已推送origin/codex/cr067-daily-repair，远端main为7aa9e98。创建/合并入口：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/cr067-daily-repair 。推送不等于已合并；云端修复已生效，无需再次部署。此次仅同步源码、测试和文档，未上传行情、模型、数据库、密钥或ignored恢复材料。
