# 市场概览上游故障处理

正式拓扑仍是 GitHub Pages 前端 + 云后端。现有云前端只保留为临时回归入口和
反向代理。本补丁不改 Pages API 地址、不代替域名/HTTPS 接入，不自动发布 main。

市场概览按阶段隔离：东方财富分页核心最多 180 秒，不重启整批采集；
单页连接/读取超时为 5/10 秒，最多两次尝试；分页间隔 0.5 秒。
完成核心后，北向资金和各指数分别有 12 秒硬上限，最多 3 个并发只读子进程。
可选阶段失败不丢弃核心快照；超时会杀死并回收进程，不遗留后台请求。
腾讯历史行情整次 SDK 调用（包含内部辅助请求）最多 40 秒，主请求另设 10 秒超时。
历史日更批次 900 秒后不再启动新请求；已有调用最多再用 40 秒，随后仍会处理概览。

HTTP `/api/market/overview` 只读最后成功快照，不再在冷缓存时同步访问上游。
没有快照返回结构化 503 `UPSTREAM_UNAVAILABLE`，前端显示暂不可用。
刷新失败不覆盖旧快照，`/api/data/status.components.overview` 标记 stale/failed；
历史行情状态独立记录在 `components.history`，包含失败标的代码。
旧数据库兼容，利用现有 cache_metadata 表与总状态在同一事务保存；旧记录返回空 components。
历史 ready 还要求资产末日一致且达到已核实日历的最新交易日；整体日期取最旧资产末日。
这仍不代表所有指标完整、所有策略已验收；历史请求会另行检查区间内交易日缺口。
概览 ready 表示核心快照采集成功；可选指标缺失记录在 unavailableMetrics 并在前端显示。
涨跌停数没有可靠价格边界时返回 null，禁止使用统一 ±9.9% 阈值推算。
北向资金、指数必须与核心快照同日；缺失成交额不能用部分合计冒充全市场成交额。

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

## 本轮验证与严格验收

AkShare 固定为 1.18.94；依赖升级必须重新验证单位、字段和缓存兼容。
东方财富沿用 AkShare 的 82.push2 主机与沪深京过滤条件，只接管分页、超时和校验。
检查总数、代码唯一性、字段、有限数值及 f124 更新时间；缺失、混合日期会拒绝发布。
这是一种保守校验：不能证明上游当前仍完整支持该响应格式，需真实全量验收。
失败保留旧缓存；没有快照则继续返回结构化 503，不会制造成功数据。

本地只读实测（不写缓存）：

```bash
PYTHONPATH=services/algorithms/src .venv/bin/python tools/check_market_upstream.py --stage history --timeout 40
PYTHONPATH=services/algorithms/src .venv/bin/python tools/check_market_upstream.py --stage spot --timeout 180
```

基础烟测仅验证启动/目录接口，不能当作 MVP 验收。真实数据更新后再运行：

```bash
python tools/smoke_regression.py --base-url http://127.0.0.1 --strict-data
```

Pages 联调还须使用已配置证书的 API HTTPS 地址，加上
`--api-only --origin https://why621.github.io --require-https --strict-data`。
这会检查 HTTP/CORS/缓存日期及覆盖信息，不代替浏览器、回测流程和负载回归。
本补丁不申请域名/证书、不改云防火墙、不发布 Pages、不重建线上服务。

## 2026-09-07 正确性与发布保护

历史区间缺失交易日时回源；回源失败、空结果、仍有缺口时明确报错，不返回部分缓存。
旧缓存保留，不自动补价。停牌、新上市缺口目前也会拒绝，待接入资产级状态后区分。
qfq/hfq 扩展区间时重新拉取整个旧缓存范围；日更 qfq 同样全区间刷新。
新响应缺失旧记录时拒绝写入，避免复权基准混用。单请求和批次时间预算仍保留。
SQLite 行情修订号与写入在同一事务提交；排名按修订号失效，最多缓存 128 个键。
排名等待和历史 I/O 使用 10 秒预算；数据变动或超时不发布结果。CPU 密集计算不是
进程级强制终止，独立任务队列和负载验收仍待完成。
日期统一到 Asia/Shanghai。离线交易日历仅核实 2025–2026 年，依据上交所年度公告；
超出年份的历史请求明确报错，2027 年前须更新日历。这不代表海外 ETF 净值公布日。
概览时间戳必须对应最近交易日；仍需真实全市场验证 f124 和停牌兼容性。
Pages 构建须配置 VITE_API_BASE_URL，例如 `https://api.example.com/api`，示例不可部署。
缺失、HTTP、Pages 自身域名、携带凭证的地址阻止构建，不再默默回落到 `/api`。
语法检查不等于证书、CORS 和真实数据验收。

本轮只读复测：腾讯返回 2026-09-03 至 2026-09-07 的 3 根日线；东方财富仍在响应前
RemoteDisconnected。尚未确认封 IP、跨境限制或具体网络责任点。
指定云服务器 SSH 22 连接超时，尚未部署。Docker 中文路径构建错误通过 stdin 上下文
越过，但本机镜像站 docker.mirrors.ustc.edu.cn DNS 失败，基础镜像未构建成功。
本地开发服务联调不能等同于 Docker 或线上回归完成。
