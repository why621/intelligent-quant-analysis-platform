# 2026-09-16 自动验收只读核查：候选成功，发布失败

本批仅只读云端核查及本地证据文档回写；未采集、重试、补跑、发布、重启、改权限或扩大预算。

07:30:01 CST timer LastTriggerUSec与service ExecMainStartTimestamp一致；systemd journal真实启动事件INVOCATION_ID=aafd66a538014705a553a945858fd333，与service和audit/20260915T233001Z.json一致；OnCalendar=07:30 Asia/Shanghai、TriggeredBy=quant-mvp-daily.timer。该证据支持真实定时运行，不以trigger=scheduled或环境变量独立认定。

state第4次尝试目标2026-09-15，07:30:03开始、07:58:59候选成功。候选5645e56543e397380ca8a827ecb158e6c5217c28d02557c3d52bfb68f7ffce37：327/327覆盖可用，ETF与指数已补至09-15，概览297有效比较+3确认停牌；SSE自动核实3条，SZSE/ETF官方停牌源仍pending。five-module.json有概览、126相关性样本、两策略回测succeeded、两条排行、09-15基础日/09-16配置。以上为候选验证，不等于线上验收。

发布失败：08:01:04 service退出1；audit failure=TimeoutError: backend readiness timeout，发布和回滚后的restart均超时。后端现处restarting/unhealthy，Gunicorn启动报PermissionError /app/publication/current.json。实际宿主指针root:root、0600，父目录0755，容器用户quant；发布指针读取权限是已证实的启动阻塞。指针内容回滚至1f3a8ff2f3a1ce2bfade6ca64d689c62a35719b89c14cd57045ec8be79b67447，但服务没有恢复，不能声称回滚成功。备份恢复报告integrity=ok、38任务，实际恢复服务与当前任务完整性未验收。

公开HTTPS /api/health返回502；/api/data/status本次TLS EOF。GitHub Pages静态HTML200，但云API不可用，无法验证数据一致性或完整浏览器链路。此次关键变化须通知用户处理发布权限及服务恢复；不应重新采集，完整候选已经存在。

预算4/4耗尽，automaticTwoDayCandidate=false；09-11成功、09-14失败、09-15候选成功不满足连续两个实际交易日自动发布验收。云timer仍active/enabled，下一09-17 07:30；本自动化权限仅只读，未更改云timer。应停止300-mvp监控；已在可用工具目录检索automation_update/automation能力，当前无可调用工具，无法执行删除，未谎称已停。需要通过自动化管理界面停止300-mvp，不得扩大采集预算。

证据路径均在/opt/intelligent-quant-cr026-20260910/daily-cr028：artifacts/cr025-daily-20260910/state.json、audit/20260915T233001Z.json、artifacts/cr025-daily-20260910/2026-09-15/five-module.json、backups/20260915T233001Z/evidence.json；另读取systemctl show/cat、journalctl真实启动事件、docker inspect状态/用户和docker logs尾部、stat权限、公开HTTP GET。未执行日更runner（包括dry-run）。本地回写未提交或推送。
