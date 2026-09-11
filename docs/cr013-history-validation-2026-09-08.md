# CR-013 逐资产历史覆盖与隔离采集验收

日期：2026-09-08；本地Windows/WSL Ubuntu，Asia/Shanghai。HEAD仍b4634d1；保留此前全部未提交修改。本轮没有提交、推送、云端访问/部署或生产数据写入。

## 结论

有界历史采集、300只完整分母的覆盖manifest、离线重放和质量检查已实现。六只真实腾讯样本都返回数据，五只覆盖242个交易日，中芯国际688981缺2025-09-08一天。官方公告证实该日停牌；不是本轮发现的服务器连接失败，也不能当作普通漏数填价。

当前自动评估器尚不消费停牌公告，688981仍为gaps且不写入候选可用缓存；原始观察保留。这是后续“证据化交易状态与研究规则”的实现入口，不把这一项改成complete凑通过率。

## 数据、粒度与范围

- 已验证名单：CR-012 snapshotId `33f99e5228a81019cdfad1c72ad2b896bce6cdb2d5416b5505723d73be95503b`；本轮没有重新下载名单。
- 请求：前复权qfq、2025-09-07至2026-09-07；市场交易日为2025-09-08至2026-09-07，共242日。
- 粒度/键：名单版本、stock/交易所/六位代码、复权、交易日期。当前名单回看一年有幸存者偏差，不代表历史成分回测。
- SDK：AkShare1.18.94；来源Tencent；项目规范化版本tx-1.18.94-project-v1。成交量规范为股、金额为元；本轮未新增跨源单位核验或除权事件经济校验。
- 观察文件是SDK及项目适配后的日线，不是原始HTTP响应字节。哈希用于检测观察/manifest不一致，不是来源数字签名或行情许可。

## 实际结果

| 股票 | 记录数/预期市场交易日 | 自动状态 | 缺日 | 无效/重复/金额缺失 |
| --- | --- | --- | --- | --- |
| 600000 浦发银行 | 242/242 | complete | 无 | 0/0/0 |
| 600519 贵州茅台 | 242/242 | complete | 无 | 0/0/0 |
| 688981 中芯国际 | 241/242 | gaps | 2025-09-08 | 0/0/0 |
| 000001 平安银行 | 242/242 | complete | 无 | 0/0/0 |
| 002594 比亚迪 | 242/242 | complete | 无 | 0/0/0 |
| 300750 宁德时代 | 242/242 | complete | 无 | 0/0/0 |

观察共1451条；仅五只共1210条进入新的候选SQLite，revision=5。全部300只始终在manifest：complete5、gaps1、not_attempted294；priceCoverageComplete=false、published=false。complete只是请求区间基本OHLCV/日期检查通过，不代表已满足全部数据质量、复权、许可或生产验收。

候选时间2026-09-08T18:50:17.806801+08:00，ID `fc02f9eed3fbc3d870129387ec15c22db1558c2933a1b7f453f8b8e03caafd9a`。本次实际18个HTTP请求（每只3个，含前置查询），均200；上限30、单只40秒、批次300秒。全部串行、禁环境代理/重定向/自动重试。重放新增HTTP请求0，条目质量与哈希完全一致。

### 停牌证据与影响

上交所披露的[中芯国际2025-024复牌公告](https://star.sse.com.cn/disclosure/listedinfo/announcement/c/new/2025-09-09/688981_20250909_2BQ9.pdf)载明A股自2025-09-01停牌，2025-09-09复牌；因此请求区间内2025-09-08无成交日线有明确停牌解释。2026-09-08通过官方公告只读核查；这部分网页调研与上述18次腾讯行情请求分开计数。

- 高优先级、证据明确：现有“所有市场交易日必须有行情”逻辑会拒绝合法停牌资产，扩大至300只前需修复业务语义。
- 修复方向：保留市场交易日分母，另外登记已核实不可交易日及证据；区分unknown gap、停牌、上市前、代码变化。研究区间/交易执行/估值的不同规则需同步契约、算法、前端与测试，不得直接删除停牌日期或补造成交价格。
- 当前边界：自动manifest中的gapReason仍unknown（未自动导入人工证据），报告对该一日给出已核实解释。未改写已生成候选，也不将241日说成242条完整行情。

## 实现与安全边界

- [覆盖评估器](../services/algorithms/src/quant_platform/data/coverage.py)：逐日集合、首尾、中间缺口、排序、重复、非交易日、必需列、有限正价格及OHLC界限、非负量额、金额缺失独立计数；不补价。
- [隔离worker](../services/algorithms/src/quant_platform/data/history_probe.py)：仅两已核实腾讯HTTPS主机，实际请求最多5次/只，连接5秒/读取10秒，响应最大2MiB。父进程硬截止；超时无法取得精确请求数时显示下界/上界，不伪报零。
- [采集/重放工具](../tools/prepare_history_batch.py)：最多6只，先验名单身份、区间及全量重放证据，再创建新artifacts目录；完整样本才保存，默认50池/旧ETF/已存行情不变，不调用update_daily/overview，不把全局DataStatus设为ready。
- [coverage.yaml](../packages/contracts/schemas/coverage.yaml)：版本1磁盘契约；HTTP API仍0.4.0，没有新增覆盖接口或生产发布器。
- 项目腾讯适配层不再对重复日期静默取最后一条，检测到则失败；SDK本身对完全重复行的处理未重写，检查边界为适配后返回。
- [可复现质量笔记本](notebooks/cr013-history-quality.ipynb)按技能要求执行：完整Schema/候选哈希/观察哈希、全名单分母、逐条重算、只读SQLite逐值核对、缺口未入库与零网络重放一致性通过。

产物均由artifacts忽略规则保护，不入库：

- `artifacts/cr013-history-20260908/{manifest.json,observations/,candidate-cache/}`
- `artifacts/cr013-history-replay-20260908/`
- `artifacts/cr013-notebook/executed.ipynb`

## 实际验证命令与结果

以下在WSL仓库根目录执行，前端测试用Windows Node。复现采集需要新输出目录且重新明确预算；不要为了复核重复联网，用--replay读取既有观察。

```bash
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools/test_check_hs300_sources.py tools/test_repair_volume_cache.py tools/test_prepare_universe_snapshot.py tools/test_prepare_history_batch.py -m 'not network' -o addopts= -q --tb=short
.venv/bin/python -m ruff check services/algorithms services/backend tools/prepare_history_batch.py tools/test_prepare_history_batch.py
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/prepare_history_batch.py --snapshot artifacts/cr012-universe-20260908 --symbols 600000 600519 688981 000001 002594 300750 --start 2025-09-07 --end 2026-09-07 --output artifacts/cr013-history-20260908
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/prepare_history_batch.py --snapshot artifacts/cr012-universe-20260908 --symbols 600000 600519 688981 000001 002594 300750 --start 2025-09-07 --end 2026-09-07 --replay artifacts/cr013-history-20260908 --output artifacts/cr013-history-replay-20260908
.venv/bin/python tools/build_history_quality_notebook.py
.venv/bin/python -m ruff check tools/build_history_quality_notebook.py
node --test --test-reporter=dot apps/frontend/tests/*.test.js
git diff --check
```

- Python317 passed、8 network deselected（15.36秒）；新增39项覆盖/采集测试包含在317内。
- 前端52项通过；Ruff和diff检查通过。未改前端实现，本轮未重新构建或跑浏览器。
- 本地真实源18次/六股票及零请求重放通过，笔记本从头执行通过；没有本轮HTTP服务联调、云端回归或发布。
- 失败记录：本机审批通信多次中断，经只读确认未执行后重试；不是行情故障。初次完整测试316通过/1失败，原因是新磁盘Schema引用根路径错误；修正引用及验证入口后317通过，未删除有效检查。
- 笔记本内核仅本机短生命周期；执行结束关闭，无新增对外HTTP服务。依赖沿用已有.venv，未新增安装。

## 下一步与MVP剩余

1. 优先T-016f：证据化停牌/上市/代码变更分类，明确研究可用区间及不可交易日规则；先用已留存688981观察离线回归，不能重拉或补价掩盖真实停牌。
2. 再扩展30—50只及完整300只，覆盖与量额/复权专项检查；现工具故意限6只，扩大前登记新预算及批次恢复设计，不静默去掉上限。
3. 独立沪深300指数、日频概览和五模块同名单/数据版本验收。
4. 两个真实交易日日更、异常告警、并发/资源限制、重启和备份恢复。
5. 源许可、域名/HTTPS/Pages及授权后的云端/浏览器回归。此次本地腾讯成功不能证明香港服务器的当前可达性或跨日稳定性。

回滚本批仅撤销新增工具/覆盖模块/契约及适配器重复日期门禁，无生产存储迁移；保留此前CR-009至012修改。临时样本保留供复核，不自动删除。
