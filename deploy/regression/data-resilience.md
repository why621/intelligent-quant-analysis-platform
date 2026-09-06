# 市场概览上游故障处理

正式拓扑仍是 GitHub Pages 前端 + 云后端。现有云前端只保留为临时回归入口和
反向代理。本补丁不改 Pages API 地址、不代替域名/HTTPS 接入，不自动发布 main。

`stock_zh_a_spot_em()` 无公开 timeout 参数，因此市场概览采集运行在独立只读进程。
每次最多 90 秒，总共两次，间隔 1 秒；超时会杀死并回收进程，不遗留后台重试。
这个时间限制仅覆盖市场概览，不覆盖历史行情的整批更新。

HTTP `/api/market/overview` 只读最后成功快照，不再在冷缓存时同步访问上游。
没有快照返回结构化 503 `UPSTREAM_UNAVAILABLE`，前端显示暂不可用。
刷新失败不覆盖旧快照，`/api/data/status.components.overview` 标记 stale/failed；
历史行情状态独立记录在 `components.history`，包含失败标的代码。
旧数据库兼容，利用现有 cache_metadata 表与总状态在同一事务保存；旧记录返回空 components。
成功仅表示本次刷新未报错，不保证资产池中所有标的的交易日期一致。

`quant-data-update` 仍保留退出码 0=ready、2=stale、1=failed。腾讯云显示代码 2
为任务失败是预期的降级告警，不能为让控制台变绿而吞掉它。
详细异常链记录到 stderr，API 仅暴露分项状态和概括信息。

契约兼容说明：新增可选 components 字段；turnoverCny 在上游缺失时允许 null，
前端已处理为横线，不能填零冒充观测值。无法验证交易日期时不发布新快照。

## 云端应用

腾讯云执行命令：root，超时 1800 秒，在现有 checkout 中先确认无本地改动，
再 `git pull --ff-only origin codex/regression-deployment`，随后执行：

```bash
bash tools/update_regression_backend.sh
```

脚本只构建替换 backend，保留数据卷，重载现有 Nginx 的后端地址，然后运行日更。
日志保存在 `/var/log/quant-data-update.log`。这不证明东方财富已恢复；若仍不可达，
应看到行情与概览各自的状态以及明确的降级提示。
Pages 前端分项提示在对应前端补丁发布后生效，分支推送本身不会更新 Pages。
