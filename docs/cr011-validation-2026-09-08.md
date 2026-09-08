# CR-011：M1范围与完整资产目录基础

2026-09-08；本地HEAD b4634d1，保留此前全部未提交M0/CR-010修改。本轮无提交、推送、发布或云端写入。

## 已交付

用户确认完整300只当前成分、保留ETF、固定名单最近一年回测、沪深300日频首页、团队内部教学演示。数据许可未自动获批。已回写四份SDD并新增 [M1设计](m1-catalog-design.md)，独立指数、名单快照、逐资产覆盖和原子发布仍是后续设计。

API 0.4.0增加目录offset、matchedTotal、nextOffset、catalogVersion、assetId。total保持本页数量；筛选后稳定排序，完整目录元数据哈希跨筛选相同、元数据变化则改变。前端读取全部分页后才发布目录，最多10页/1000条，混版、重复、数量/偏移异常、上限及旧接口缺少元数据均明确失败；重试成功清除提示，过时请求不再追加分页。

provider内部limit=None返回完整内存目录，历史资产、回测资产及ETF基准校验不再截断到100条。HTTP单页上限仍100，默认50；默认50只混合资产池、行情存储和历史完整性逻辑不变。新增身份仅元数据，当前研究API仍为六位股票/ETF请求，不支持独立指数。

## 实际验证

1. 先运行新增8项后端离线测试：全部失败，分别重现缺分页字段、offset不校验、目录尾部资产被误拒；实现后8项通过。
2. 完整Python：248 passed、8 network deselected，15.51秒。命令：

```bash
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools/test_check_hs300_sources.py tools/test_repair_volume_cache.py -m 'not network' -o addopts='' -q --tb=short
```

3. 前端：npm test --workspace @intelligent-quant/frontend，52 passed（新增13项）。npm run build:frontend通过，主包index-DUFgn_KX.js。
4. 静态：.venv/bin/python -m ruff check services/algorithms services/backend tools/serve_m0_local.py 与 git diff --check通过。首轮调用不存在的.venv/bin/ruff未执行检查；改用已有Python模块，修正一处导入排序后通过。
5. 本地浏览器：现有tools/serve_m0_local.py复用artifacts/m0-20260908三个ETF缓存，未运行prepare；仅监听127.0.0.1:8765。运行：

```text
node tools/verify_m0_browser.cjs http://127.0.0.1:8765 artifacts/cr011-browser
```

使用已有Playwright与Edge152.0.4191.66，13场景通过、pageErrors为空。真实目录新分页请求、相关性241样本、两策略及ETF比较各242点、任务恢复、故障和现金边界复验通过；全现金空持仓场景仍为明确fixture，不是行情证据。证据：[evidence.json](../artifacts/cr011-browser/evidence.json)。服务测试后已Ctrl+C停止。

## 证据边界与未完成事项

- 后端合成300股票+101ETF目录，额外ETF用于复现基准第101条截断；前端合成300股票+1ETF。这些是隔离假数据测试，绝不是官方成分名单或真实行情。
- 浏览器仅既有3只真实ETF缓存；没有300只真实行情、本次外部数据源验证、独立指数或新概览验收。旧概览仍503，未用0填充。
- 本轮不改变云端。当前前端需要0.4.0分页元数据，若配旧后端会提示目录不可用；发布时先部署兼容旧客户端的新后端，再更新前端，且需当次授权。
- T-015/M1仍进行中：本批完成范围和目录基础，逐资产覆盖/独立指数的具体实现契约仍待补齐。T-003源选择/许可、M2真实全量数据、M3概览、M5日更恢复、M6HTTPS/Pages均未完成。
- 审批服务多次传输中断；确认未执行后重试成功，不是产品或数据源故障。真实缓存和浏览器产物仍在Git忽略目录；已有数据未删除。

## 下一批入口

收尾只读检查：9份Markdown、100个本地链接、UTF-8及代码块配对通过；git diff --check通过。HEAD仍b4634d1、暂存区无新增；浏览器证据由artifacts规则忽略；ss确认8765无监听。

先读取本报告和M1设计，再完善可追溯名单快照、指数独立身份与覆盖manifest契约及离线校验；核验真实名单来源、日期和唯一300成员，再在隔离数据目录完成子集到全量验证。不能只把默认池换成300个代码就标记MVP完成。回滚本批不需要数据库迁移，未涉及线上回滚。
