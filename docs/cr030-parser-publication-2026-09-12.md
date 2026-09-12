# CR-030 解析修复与已有候选发布验证（2026-09-12）

## 当前结果

本地解析协议修复完成，18项专项离线测试通过，已有09-11候选在云端禁网容器中重新通过五模块验证。两份源码上传被自动审批明确拒绝，因此修复未安装到云端，未执行已有候选发布，线上仍为09-09旧版本。不能标记整个用户任务完成。

## 实际修改

- tools/daily_publication.py：execute期间stdout重定向到stderr，stdout只输出最终单个JSON；不改变采集、日期、预算或账本。
- tools/run_cloud_daily.py：parse_outcome严格验证单个JSON及decision，不接受夹杂进度的输出；新增互斥参数--promote-existing，直接读取最新成功账本及候选，跳过runtime及采集进程；保留版本哈希、维护、排空、备份、原子切换和回退。审计mode=manual_existing_candidate，invocationId=null，不冒充自动发布。
- tools/test_run_cloud_daily.py：混合进度/结果输出复现、非法输出拒绝、已有候选模式禁止任何采集调用并核对账本不变和维护标志清理。
- 无产品API变化，本批先在四份SDD登记CR030再修改实现；已有用户修改保留。

## 已执行验证

`PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest -q tools/test_run_cloud_daily.py tools/test_cloud_publication.py tools/test_daily_publication.py tools/test_cr026_release.py`：18 passed in 13.71s。

Ruff：执行器和新增测试通过；两文件新增import顺序已修正。daily_publication全量Ruff仍有既有RUF007相邻迭代和BLE001捕获Exception两条；未借此改变连续交易日算法或失败记账行为，不宣称全部Ruff通过。

云端已有候选禁网复验：固定现有镜像、只读挂载publication/tools、临时任务库，docker --network none运行verify_published_provider.verify(load_publication(...))，通过。候选版本a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a，截止09-11；概览300/300，涨55/跌237/平8；含例外资产十资产相关性125共同区间样本；两策略指数回测succeeded；两策略排行；配置basis09-11/target09-14、持仓加现金100%。这属于隔离候选验收，不是线上切换或Pages新版本验收。

真实早间候选五模块报告也已读取：artifacts/cr025-daily-20260910/2026-09-11/five-module.json。账本SHA256=8dd9a85f809cfac4311246d356c0f2bdd2c09c8bdf6e5d1299be6e89480eb258；本轮未重采或修改账本，使用2/4、剩余2次。

## 待上传的具体内容与阻断

- tools/daily_publication.py：6271字节，SHA256 b30926ed5bc4efba4d538e3b68f93a6d73f36f6a211e5cdd893ada2e99394ac3。
- tools/run_cloud_daily.py：6995字节，SHA256 930f2626621a304e9dd66bbeaa09f9dafc4a6a67d4339842a59a6949afc3d5bf。

共13266字节，两份运维源码，不含行情、任务库或密钥。目标43.161.223.91，临时文件/home/ubuntu/cr030-*.py，核对哈希并备份后安装至/opt/intelligent-quant-cr026-20260910/daily-cr028/tools/。

SCP未执行。自动审批拒绝理由：用户授权修复和候选验证，但未在可信用户内容中明确授权这两个具体源码文件向该目的地外传。不能绕过，需用户明确允许上述两文件到上述服务器。既有一般云部署授权未被审批器认定覆盖此次具体源码外传。

## 解除阻断后

1. 校验两份文件哈希，备份旧工具并安装；执行禁网dry-run验证JSON输出。
2. --promote-existing仅发布已验证候选，复用维护、排空、备份、切换和探测/回退门禁；不重采、不手改账本。
3. 核对公网HTTPS版本、五模块、Pages接入及旧任务恢复，比较账本哈希不变并保存发布审计。
4. 回写真实结果。早间自动采集加本次人工恢复发布不得记为完整自动发布，更不能算连续两个实际交易日验收完成。


## CR-030 授权后发布与最终回写（2026-09-12）

用户明确授权两份源码及43.161.223.91目的地，上传阻断解除。上传前一次审批通信中断未执行；核对本地哈希后重试成功。两文件云端哈希与本报告一致，旧文件已备份到daily-cr028/backups/cr030-tools后安装。

- 禁网dry-run返回already_attempted、targetDate=09-11；随后仅执行`python3 -m tools.run_cloud_daily --promote-existing`，未运行采集。发布前后state.json SHA256均为8dd9a85f809cfac4311246d356c0f2bdd2c09c8bdf6e5d1299be6e89480eb258，预算2/4、剩余2次不变。
- 云审计`daily-cr028/audit/20260912T093705Z.json`记录17:37:05—17:37:14 CST，mode=manual_existing_candidate、invocationId=null、promotion.status=promoted；候选版本a668248b3881cbed35e6b57e8372b0403c09a8738fe86b157425ce2dcf7fdd5a、截止09-11。维护标记已移除，备份及旧指针位于backups/20260912T093705Z。发布前恢复检查integrity=ok、18条任务一致。
- 线上严格HTTPS状态ready、327资产、截止09-11；发布探针已验证概览300/300同版。18个发布前任务经线上API逐个对比状态、请求、结果全部一致。第一次校验容器只读打开备份失败，改为主机只读immutable打开备份并由后端容器查询API完成验证，未改线上任务库。
- 真实Edge打开GitHub Pages，327目录正常；页面浏览器上下文通过实际CORS调用状态、概览、两策略排行、3ETF相关性及模拟配置，全部200且同一新版本，failedRequests=[]。配置basis09-11/target09-14、现金加持仓100%。证据及页面截图在artifacts/cr030-browser-20260912/evidence.json、pages.png。研究请求由浏览器fetch验证，本轮不冒称全部按钮重新操作或人工像素复核；新批次两策略指数回测已在此前禁网候选五模块复验通过，本轮未额外创建线上回测任务。
- timer仍active，下一次09-13 07:30 CST。服务早晨失败记录保留，不用清日志或reset-failed掩盖历史；本次手动发布进程成功是独立证据。

结论：解析修复已安装，已有候选发布及新版本Pages接入验证完成，旧任务保留，未重采或扩大预算。此前本报告和交接中的“未上传/未发布”已成为历史，不再索取相同授权。此次是自动采集后的人工恢复发布，不计完整自动更新成功日；连续两个实际交易日自动采集与自动发布仍待后续真实调度证明，不宣布全部MVP验收完成。真实云切换成功已验证，故障注入回退仅有既有离线证据，未额外声称完成线上故障演练。
