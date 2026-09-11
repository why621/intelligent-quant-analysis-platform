# CR-021 图表与本地浏览器验收

无有效基准时不生成基准序列/图例，净值tooltip固定4位且不改变原始数据；相关性色条禁用拖动手柄，锚点分别适应桌面/平板/移动布局。

前端54项测试通过、WSL npm run build:frontend通过（上轮）。本轮修正浏览器脚本等待真实净值而非占位SVG、修复Ruff测试导入排序。

实际命令：NODE_PATH指向已安装Playwright运行时，node tools/verify_cr021_browser.cjs。Edge本地真实三ETF缓存副本、真实worker：相关性与回测上下文一致、无基准曲线图例正确、旧截止配置503 DATA_STALE；1440/820/390宽度锚点均不遮挡、页面无横向溢出、pageErrors为空。任务949b86b8-920a-46ea-bdfd-31904375c6f0 succeeded。证据及截图：artifacts/cr021-browser-20260910。首次脚本误等占位SVG，读到queued，已修正并真实重跑成功，没有注入成功响应。

原行情/任务库通过SQLite只读备份复制到artifacts/cr021-browser-local-20260910；验证新任务只在副本。测试服务只绑定loopback并禁止上游；不等于300池联调、日更或云发布。审批连接间歇中断，经用户重试授权及只读核查恢复，未绕过限制。
