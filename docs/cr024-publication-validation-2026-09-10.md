# CR-024 完整本地发布与五模块联调

完整300股票（289完整、11已解释例外）+27ETF+沪深300价格指数已组装到artifacts/cr024-publication-20260910。截止2026-09-09；publicationId e5f794c7094c21c2ba08903c0c5697904f0d4b0f87a3312e6285f0f4c95634fe。发布包完整验证后原子替换current.json；运行中读者固定已载入版本，新服务进程才载入新指针。离线篡改/缺口/中断保留旧指针/旧读者固定/覆盖API 3测试通过，非日更验收。

实际联调命令：PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python tools/serve_publication_local.py --publication artifacts/cr024-publication-20260910 --jobs artifacts/cr024-local-jobs-20260910/backtests.db；Windows已有Playwright NODE_PATH下执行node tools/verify_publication_browser.cjs。

2026-09-10真实Edge与本地worker：
- 327资产四页目录及327覆盖条目通过，同一published_snapshot上下文。
- 概览：141涨、150跌、9平，比较覆盖300/300；成交额440048388500元，仅300成分；沪深300价格指数4572.6。北向/涨跌停未知仍null。
- 含停牌/上市前资产的10资产45对相关性：123共同区间样本；3ETF页面矩阵实际交互成功。
- 无基准页面回测07fd280f-e0e7-4ae6-a4fe-6eebe6f5fd9f成功，图例无空基准。
- 指数基准API回测：ma_cross任务190ca9d0-01a0-4789-bf09-a1b9723e296c，momentum_reversal任务d6e52ed1-2370-4055-8249-085fd81700b2，均succeeded。使用服务端Schema默认参数，未削弱必填检查。
- 两策略排行、配置同版本；配置basis09-09、target09-10，持仓+现金100%。
- 1440/820/390屏宽锚点无导航遮挡、横向溢出0，pageErrors为空。

最终复验（2026-09-10）：完整Python离线回归375 passed、8 network deselected（42.31秒）。首次全量回归369通过、1失败，原因是新增/data/coverage未同步接口清单断言；补齐清单后全量通过，保留全部契约检查。命令：

```sh
QUANT_DATA_DIR=artifacts/cr017-test-cache PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools -m "not network" -o addopts= -q --tb=short
```

前端最后修正了不可变发布标签，54测试及构建重新通过。最终浏览器脚本 `node tools/verify_publication_browser.cjs` 通过，证据和截图位于 `artifacts/cr024-browser-20260910/`。新增实际UI操作：十资产输入/矩阵、独立指数基准回测、页面刷新后恢复原任务且无新POST、生成模拟配置；显式注入503仅验证故障时禁用提交，成功结果来自真实本地服务。未将故障注入冒充真实源故障。

最终无基准任务2ce074cb-8337-4b7a-930a-f1e9fa807acc；两策略指数API任务422f28a7-37fc-41fb-8447-977676c20e3e、82c4dae9-1cb3-404f-993a-19700d99be2a；UI指数任务29657c6b-e188-42e8-88ee-f7ca5cee2668，均成功。前文任务是较早通过记录，独立本地任务库保留。扩展脚本首次误按下拉控件查找相关性输入超时，核对实际六位代码输入控件后修正通过，没有修改业务实现来绕过检查。

自动更新使用的五模块门禁已对同一发布零网络复验，`daily-gate.json`保留两个指数回测结果。本地功能、五模块和浏览器交互验收通过；连续实际两交易日转入[CR-025报告](cr025-daily-acceptance-2026-09-10.md)，已启用每日07:30调度但尚无实际两日成功证据。云上线、Pages HTTPS及许可验收仍独立未完成。最终人工视觉复核已查看十资产矩阵、完整指数净值曲线及390宽度计算后页面。发现并修正旧池误标签；截图等待图表动画结束，避免半绘制截图。自动几何断言三种屏宽仍通过。

最终标签与截图复验任务（以当前evidence.json为准）：无基准 bc8b9e12-83d5-401d-b149-2faf4be15c23；指数API 44c359b6-9222-4644-a4c2-ad114d76f706, d3238a9c-a1f2-40d8-a199-60e56ef460aa；指数UI/恢复 199c0701-8f0f-4765-8e4d-9a5f29dfd20a，全部succeeded。
