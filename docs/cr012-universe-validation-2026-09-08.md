# CR-012：真实沪深300名单快照与目录验收

2026-09-08，本地HEAD b4634d1；在CR-009/010/011未提交修改基础上继续。没有提交、推送、部署、线上数据修改或全量行情抓取。

## 本轮结果

官方当前名单已保存并严格校验为300个唯一股票：上海189、深圳111。源文件日期2026-09-07，下载时间2026-09-08 17:53:43.763799 +08:00，源日期距下载1个自然日。只证明该次快照结构与来源可追溯，不证明调样生效日期、历史成分、后续持续新鲜度或行情许可。

来源：[中证官方000300成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000300cons.xls)；官方详情页为JavaScript页面，名单文件是本次实际解析证据。

- 原文件SHA256：2ddc7fec2c09f53007cc3c8db9e3383cbb77a88395616bfbfc5aa950a85ae1e2。
- snapshotId：33f99e5228a81019cdfad1c72ad2b896bce6cdb2d5416b5505723d73be95503b。
- 在空行情隔离库中显式加载该快照，真实Flask测试客户端返回300股票+27旧ETF，共327项，分页偏移0/100/200/300；尾部302132可查询。
- 空库的latestTradeDate仍为null，回测返回503 DATA_NOT_READY。名单加载不会自动宣布行情就绪。

## 实现和契约

新增universe.py：明确中英表头解析、指数000300/沪深300身份、300条唯一股票、交易所/代码一致、非空名称、同一且非未来源日期；不可变成员、原文件哈希与快照哈希。保存仅创建新目录，读取重新解析原文件并核对规范化JSON。哈希用于一致性/篡改检测，不是官方签名，不能证明许可。

磁盘契约新增packages/contracts/schemas/universe.yaml，版本1；不是新增HTTP路由，现有API仍0.4.0。sourceDate不冒充effectiveDate，后者null；historicalMembershipVerified固定false。

provider仅显式传入universe_snapshot时加载300股票并保留27ETF。create_app增加显式provider注入，所有服务共享该实例；默认启动和数据更新器仍使用旧50池。没有生产配置开关、名单自动切换或行情迁移，不能仅凭本批代码部署就认为全量数据已接入。

## 检查过程和失败证据

采用数据质量检查流程：先明确颗粒度/唯一键、日期和下游用途，再检查完整性、唯一性、身份一致性、来源和时间，保存可重跑笔记本。

1. 官方名单共请求2次，均取得文件；第一次解析因“成份券代码”与“成分券代码”别名不匹配拒绝。第二次先保留原文件，之后全部离线重放，HTTP预算没有增加。
2. 原文件300行9列。补明确“成份/成分”别名后又发现“交易所英文名称”被宽泛前缀误匹配；改为精确中英表头映射，并测试重复/歧义列仍拒绝。没有按列位置盲目重命名或取消质量检查。
   严重性高、判断置信度高：旧解析方式阻断整份真实名单接入，已由保留原文件稳定复现；修复是明确列名映射及回归。其余质量规则未发现失败，必需字段完整、唯一键与指数/日期一致性均为300/300；这不构成历史行情或授权通过证据。
3. 实际校验：300/300唯一代码与身份、所需字段非空、189/111交易所、300行同一指数和日期、非未来日期；原文件与快照重读一致。无法从一个当前快照分析历史调样、历史趋势或一年行情质量，未作此类结论。
4. 首轮离线测试因缺jsonschema而未收集成功；保留完整Schema检查，将jsonschema加入dev依赖后重跑。内置文档Python缺nbformat，使用项目独立notebooks可选依赖组执行，不修改系统Python或内置依赖目录。
5. 审批服务多次连接中断；只读确认未执行后重试。一次只读XLS命令引号失败，改为标准输入执行同一只读检查。不把这些工具失败算成上游网络故障。

## 实际验证

```bash
# 初次获取（本轮仅两次；今后优先重放，不重复此命令消耗预算）
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/prepare_universe_snapshot.py --output artifacts/cr012-universe-20260908

# 本轮成功的零网络重放（输出必须是新目录；已有结果不能覆盖）
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/prepare_universe_snapshot.py --input-download artifacts/cr012-universe-20260908-download --output artifacts/cr012-universe-20260908

# 本轮目录验收；复跑需指定另一个新输出目录
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/verify_universe_catalog.py --snapshot artifacts/cr012-universe-20260908 --output artifacts/cr012-catalog-20260908

# 全套离线：278 passed / 8 network deselected，15.73秒
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools/test_check_hs300_sources.py tools/test_repair_volume_cache.py tools/test_prepare_universe_snapshot.py -m 'not network' -o addopts= -q --tb=short

# 伴随笔记本：从头到尾执行成功，无网络请求
.venv/bin/python tools/build_universe_quality_notebook.py
```

前端node --test --test-reporter=dot apps/frontend/tests/*.test.js为52项通过；npm run build:frontend通过，主包仍index-DUFgn_KX.js。Ruff检查services及新增工具通过，git diff --check通过。本轮没有浏览器或云端验收；此前13个浏览器场景属于CR-011，不能当本轮327项浏览器通过。

核心新增回归包括真实格式别名、未来/混合日期、非目标指数、重复/非法代码、交易所矛盾、空名称、数量不足/过多、原文件与JSON篡改、重复保存、HTTP重定向/重试拒绝、大小/时间上限、输出路径越界、重放篡改无HTTP。合成测试数据不当作真实成分。

## 证据与复现

- [质量摘要](../artifacts/cr012-universe-20260908/quality-summary.json)。
- [目录API证据](../artifacts/cr012-catalog-20260908/catalog-evidence.json)。
- [复核笔记本源码](notebooks/cr012-universe-quality.ipynb)；[已执行笔记本](../artifacts/cr012-notebook/executed.ipynb)。
- 原始XLS、真实快照、空行情测试库、执行产物都在artifacts忽略目录；仅源代码/契约/汇总文档和无原始成员输出的笔记本可纳入后续审阅。

## 距完整MVP剩余

| 剩余项 | 当前缺口 | 退出门槛 |
| --- | --- | --- |
| 300只一年行情与覆盖 | 名单已确认；未抓取/验收全量股票历史 | 逐资产来源/复权/单位/日期/缺口明确，停牌/新上市/换码有证据；版本化发布，不伪造价格 |
| 独立沪深300指数 | 当前只有明确ETF或无基准过渡 | 指数单独适配/存储/请求身份，真实指数比较及缺失处理通过 |
| 沪深300日频概览 | 原全市场概览仍不可用 | 真实成分涨跌/成交活跃度与指数，日期、范围、有效覆盖明确 |
| 五模块全量一致性 | 旧子集默认路径已验证 | 相关性/回测/排行/配置/概览绑定一致名单与数据版本，327目录真实浏览器验证及负载测量 |
| 日更与可靠性 | 缺自动日更/告警及恢复证据 | 两个实际交易日自动更新、重启/备份恢复/源失败演练，限额及依赖可复现 |
| HTTPS/Pages与发布 | 域名/HTTPS、许可和发布授权未齐 | 有效HTTPS、CORS、真实Pages五模块、云端回归与可回滚发布 |

不以测试数量推算MVP完成百分比。AI/海外/实盘不在本期。下一批按名单快照补逐资产覆盖manifest及历史采集协调器：先隔离少量沪深样本核对日期/单位/复权，再逐步扩展完整300；不能删掉有效检查或因缺数据随意剔除成分。独立指数随后按单独源验证推进。
