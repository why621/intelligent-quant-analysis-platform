# CR-020：独立沪深300价格指数

显式身份index:CSI:000300，腾讯sh000300指数端点，价格指数、点、无复权；不以000300股票或510300ETF替代。基准选项仅在注入已校验指数快照时开放，缺失明确失败。版本上下文包含指数快照哈希；Alpha/Beta覆盖独立协方差计算及零协方差有效beta=0。

外部验证：明确最多2次HTTP/45秒/原始2MiB预算，实际1次200；artifacts/cr020-index-probe-20260910保存原响应及trace。响应返回640行，解析器按目标日期过滤并验证指数名称/代码、day序列、OHLC、顺序和完整交易日。

零网络构建artifacts/cr020-index-snapshot-20260910：2025-09-09至2026-09-09共243条；snapshotId bfa72598314dc4e497efdf639eb4b5893ac5a8d158ac14946f5aed464fd74075，原响应SHA256 f2f375252abce5fe1d903e775a686317e097148ff6cc2cadf7cedce08e0346e6。

契约OpenAPI 0.6.0、后端显式基准校验、算法和前端选项同步。research_publication测试11 passed，包括真实SQLite任务执行和版本变化；此前完整离线363 passed/8 deselected。前端54测试通过、WSL npm run build:frontend通过。

未自动装载到默认运行池，需随完整发布批次接入；本批没有云端/浏览器/连续日更验收。
