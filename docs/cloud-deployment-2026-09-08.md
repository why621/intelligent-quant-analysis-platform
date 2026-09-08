# 云端缓存修复与研究链路部署验收

日期：2026-09-08；CR-006 / T-013。用户本轮明确授权尝试云端部署。

## 结果与边界

后端代码`a9c1b95`已部署到43.161.223.91。云端真实HTTP历史、相关性、异步回测及后台执行、排行、模拟配置通过；本机直连公网health为200。不是完整MVP：市场概览仍503，当前仍50只股票/ETF混合池，未切换沪深300子集/完整300只，没有Pages HTTPS或浏览器验收。

未推送GitHub；使用增量Git bundle将本地发布提交传至用户云服务器并快进。原有云前端容器未重建，只reload Nginx后端地址；没有把云前端改成最终发布架构。

## 发布与回滚标识

- 服务器目录：`/opt/intelligent-quant-regression`。
- 部署业务提交：`a9c1b95d778b6b83b4e61a1c07b30fc2d6595d69`；之前为`d9f0798`。
- 当前镜像：`intelligent-quant-regression-backend:release-a9c1b95`，运行ID `sha256:b4dc5e843dfe6636d08740251dd4c1f479895909f5e367a2c49552340192db15`；latest同版本。
- 原镜像保留：`intelligent-quant-regression-backend:rollback-d9f0798`，ID `sha256:a67a0d5e7f4ef5d4861bf9d331faa86058eae66d2b1b961782184f17cafe3add`。
- 完整成功备份目录：`/opt/intelligent-quant-backups/a9c1b95-20260908-r2`，仅root可访问。
- 备份包含`repository.bundle`、`backtests.original.db`、`volume/market_data.original.db`及`volume/staged/market_data.db`修复副本。未删除原数据卷、旧镜像、备份。
- 首次失败尝试目录`/opt/intelligent-quant-backups/a9c1b95-20260908`保留，仅有不完整准备内容，不能当成功备份使用。

## 迁移实现与证据

[repair_volume_cache.py](../tools/repair_volume_cache.py)默认仅准备，`--apply`才应用。必须使用新备份目录；先SQLite一致性备份、隔离副本完整重拉，所有目标通过后才进入原库单事务。应用前核对完整逻辑摘要，阻止准备期间原库改变；只替换目标历史与标记，不整库覆盖。

本次目标均qfq，区间2025-08-04至2026-09-07：000001、000333、000568、000725、000858，每只267条，共1335条。全部重新通过腾讯采集和日期/OHLCV/amount非空校验，没有对原库盲乘100。

应用后只读对照：

- 其他45只资产历史双向SQL EXCEPT差异均为0。
- 五只目标各267条均存在；相对备份成交量恰为100倍，收盘价变化条数为0。这是重拉后的对照结果，不是修复算法以旧值乘100生成行情。
- 五个规范标记均为`tx-1.18.94-sz000-shares-v1`。
- 既有日更状态没有伪造为本轮全量更新：保留2026-09-07快照、50只history ready、overview failed、整体stale。本轮只重拉五只，不声称50只再次日更。

维护期间停后端；核查未发现项目行情更新cron/systemd timer，只有云平台及系统任务，没有禁用这些系统任务。

## 失败与恢复记录

第一次在任务库只读挂载备份阶段遇到SQLite unable to open database file，尚未应用行情修复。文件存在，停写后使用只读不可变连接且确认无非空WAL，解决只读挂载下WAL元数据创建问题。第一次失败触发自动恢复旧镜像，旧服务healthy。

第二次使用新备份目录，备份、五只采集、事务应用、新后端健康检查均成功。原镜像和数据库保留。首次回滚证明服务恢复路径可用，但**没有执行迁移成功后再整库恢复的数据回滚演练**。

如需回滚，先停API和项目行情写入，确认准确备份目录及当前期间是否新增任务/行情，再选择只回滚代码或配套恢复行情库。恢复行情应使用SQLite backup API，保留现有库作为额外备份，不递归删除数据卷；任务库不可无条件覆盖，以免丢掉发布后新增任务。启动旧镜像后reload Nginx并重新验收。旧代码重新抓取000数据仍有单位问题，回滚不是质量修复。

## 验证分层

| 层级 | 本轮实际结果 |
| --- | --- |
| 本地离线 | 220 passed、8 network deselected；含迁移成功、失败不部分应用、原库变化拒绝、日期缺失拒绝、准备只读/备份新建保护 |
| 静态/前端 | Ruff通过；前端12项通过；Vite生产构建通过；diff检查通过 |
| 新云镜像隔离 | 腾讯三样本各242条，缓存重读与研究API通过；无生产卷挂载 |
| 云服务HTTP | health/status/history/correlation/ranking/allocation为200，回测提交202，后台实际执行后succeeded |
| 公网本机直连 | `http://43.161.223.91/api/health`为200；`/api/market/overview`为503 |
| 未验收 | 全量沪深300、首页数据、日更调度、Pages HTTPS/CORS浏览器、负载、完整备份恢复演练 |

云端HTTP样本：000001、600036；回测区间2026-06-01至2026-09-07，ma_cross参数5/20，基准明确为510300ETF（非指数）；配置basisDate为2026-09-07。真实持久化测试任务ID：`56eb8d9d-13e5-4099-93cb-555410170153`，未删除该测试记录。

环境：云Python3.12.14、AkShare1.18.94，新镜像解析pandas3.0.5；Docker提示缺buildx但构建成功。原有非AkShare依赖是范围约束，后续需要独立锁依赖任务，不据此承诺每次重建完全相同。

复验命令（云服务器；会新增一个研究回测任务，无真实订单）：

```bash
sudo python3 /opt/intelligent-quant-regression/tools/verify_cloud_research.py --base-url http://127.0.0.1 --end-date 2026-09-07
```

该日期仅用于本次记录；以后配置建议需匹配当时实际截止交易日，不将旧日期脚本通过当作最新数据验收。

## 后续

1. 确认首发30—50只标注子集还是完整300只；固定名单历史回测范围、首页统计语义和使用授权仍待确认。此次部署未替用户做这些范围选择。
2. 接入可追溯成分名单与独立指数提供器，按规格实现目标资产池；保留旧ETF数据，不能悄悄将ETF作为指数。
3. 首页概览方案经确认后实现并验收；当前503明确保留，不能删严格检查掩盖。
4. 补日更调度、域名HTTPS和Pages浏览器验收；当前云HTTP入口仅回归测试，不上传敏感信息。
