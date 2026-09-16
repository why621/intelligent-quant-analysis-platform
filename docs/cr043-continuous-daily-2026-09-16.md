# CR043 持续日更


## CR043 持续日更（2026-09-16，登记）
用户明确要求持续日更并启用每天Asia/Shanghai 07:30。新增显式continuous模式，独立artifacts/continuous-daily账本/候选，保留原cr025四次验收账本及门禁不变。持续运行直到明确停用，不设置累计四次或连续两日即停止；同一目标交易日最多尝试一次，07:30取昨天及以前最近已完成交易日，休市/已发布日期跳过，不追补历史日或同日自动重试，Persistent=false不在开机补跑。请求1637/采集5400秒/外层6000秒、容器资源/并发锁不放宽；至少2GiB可用磁盘后才开始新候选，无自动删除原证据。失败保留线上快照，部分资产按既有部分发布规则验证；发布备份/回滚/0644修复继续有效。失败写独立审计及systemd journal，不引入对外通知渠道。dry-run禁网且不创建采集尝试。原四次验收成败不修改，持续模式不伪称两日验收通过。备份部署两工具及明确systemd模式参数，检查下一触发时间；首次实际采集等下一07:30，不手工抢跑。测试独立账本、跳过/去重、四次后与连续两日后仍可继续、失败发布保护及禁网预检，逐批回写。


## CR043 实现、验证与启用结果（2026-09-16）
已新增daily_publication --mode continuous和run_cloud_daily --mode continuous。独立账本artifacts/continuous-daily/state.json及候选publication，旧acceptance默认行为与4次停止规则保留；continuous累计4次/连续2日不会停止，但目标已发布或同日已有attempt会跳过，不重复发布旧候选。独立账本必须标mode=continuous，防止拿旧验收账本当持续运行账本。新候选前可用磁盘须>=2GiB，失败不删除原始证据；日历超范围或来源异常仍失败记录，不制造交易日或行情。
测试命令PYTHONPATH=.:services/algorithms/src:services/backend/src .venv/bin/python -m pytest tools/test_daily_publication.py tools/test_run_cloud_daily.py tools/test_cloud_publication.py tools/test_data_maintenance.py -q -o addopts=：80 passed，50.86秒。覆盖两模式、旧预算、连续日/累计次数、独立账本、禁网dry-run、低磁盘禁采、跳过日不发布、已有候选无采集、失败保护及CR042权限修复。未改接口或前端，不重复浏览器构建测试。
云部署完成：/opt/intelligent-quant-cr043-20260916保存工具/systemd原配置备份；包SHA256 15f06d68f9eadbd870a0c539aa2da17e7dc6b411e7d3d7344047b830cc367512。安装daily_publication.py、run_cloud_daily.py及已修复cloud_publication.py。通过systemd service.d/continuous.conf显式ExecStart=/usr/bin/python3 -m tools.run_cloud_daily --mode continuous，timer原07:30 Asia/Shanghai、Persistent=false和原资源限制保留。维护与发布不在本次启用时执行。
云端--mode continuous --dry-run使用network none，结果waiting_new_day、targetDate=2026-09-15、mode=continuous、maxRequestsPerAttempt=1637。新账本{"mode":"continuous","attempts":[]}无采集记录；原账本SHA256 30882eed4c62071bc96d07d71cab44a26263a22eae9a7d432496ece6e7e4fd83未变，线上指针字节不变，仍完整5645e565/09-15。
最终systemctl证据：timer ActiveState=active、UnitFileState=enabled、NextElapseUSecRealtime=Thu 2026-09-17 07:30:00 CST；service ExecStart含--mode continuous，当前inactive是等待定时触发的正常oneshot状态。未启动今日采集。日志artifacts/cr043-continuous/deploy.sh.log以及云stage/deployment.json。追加只读磁盘/HTTPS检查被自动审核通信故障中断，未取得新证据，不影响上述已完成部署与启用。
下一次将处理09-16或届时日历确定的最近已完成交易日，休市/同目标跳过；每次1637请求/5400秒采集上限、外层6000秒及容器限额、锁、备份/回滚和逐资产门禁维持。任务失败写audit和systemd journal，无新增邮件/消息主动通知渠道；不能把日志留存说成已配置外部推送告警。历史四次验收仍4/4耗尽且未完成连续自动两日，本模式的实际自动采集/发布需从09-17真实触发后观察，当前是已启用而非已验证长期稳定。
本地源码与文档尚未Git提交/推送，云工具已配套安装；新模式无累计次数上限，持续至明确停用。运维停用：systemctl disable --now quant-mvp-daily.timer（不清空任何账本）。旧300-mvp任务监控仍使用历史验收指令且本会话无automation_update能力，不应由该旧监控自动停掉新持续timer；后续只读监控需以本CR043为当前入口。


2026-09-16完整同步入口：按用户要求将CR041前端恢复、CR042发布权限、CR043持续日更的源码/测试及中期文档汇总至新分支 codex/mvp-complete-updates-20260916。本分支包含此前尚未Git提交的6份工具和测试，前文“源码未提交/仅同步文档”是历史状态。无新增采集、云发布或运行规则变更；既有80项专项回归及前端68项测试证据沿用，不重复累计。用户合并此汇总分支即可，无需再分别合并旧CR041分支。
