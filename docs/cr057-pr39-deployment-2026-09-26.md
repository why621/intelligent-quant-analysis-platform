# CR057 PR39配套部署


## CR057 PR39修复合并与配套部署（2026-09-26，登记）
用户确认PR39合并并明确要求云服务器及GitHub Pages上线，承接此前文档回写授权。基线main 1aa761cf307ceda1dd4e005f595dab914ad4d57f，修复c7ad7d4。范围：日历包资源、只读研究缓存、Web样本外验证边界及节假日测试修复；沿用现有四实验模型，不上传权重、不重训、不采集、不改07:30持续规则或重置账本。
验收：467离线通过/2可选跳过/14联网排除与wheel独立导入证据沿用；合并CI三项成功。新源码镜像先禁网候选五模块和旧模型回归，维护门禁排空、SQLite备份实际恢复后切换，失败恢复旧镜像/配置；核对行情指针、任务和两份账本未改。Pages本次无前端路径变更，核对最新成功发布的前端树与main一致，并在实际Pages验证新云后端，不因无源码差异制造重复前端发布。结果逐批回写；尚未通过的云端/浏览器项不先标完成。


## CR057 最终交付（2026-09-26）
PR39于2026-09-26T14:16:48Z合并，main为1aa761cf307ceda1dd4e005f595dab914ad4d57f，修复提交c7ad7d4。合并前后算法、后端、整栈回归CI均通过。本地修复回归467 passed、2可选模块跳过、14 network排除，Ruff/diff检查通过；wheel实际离线构建并在独立解包目录导入2014—2026日历、核验2020-01-31休市通过。不是本轮重新训练或重新采集。
修复内容：日历JSON迁至services/algorithms/src/quant_platform/data/calendar_closures.json并配置package-data；研究训练使用SQLite mode=ro、query_only，不建库/不迁移/不补拉，拒绝默认线上缓存目录；Web样本外起点、请求及排行统一使用in_sample_end；测试夹具使用latest_session，解决节假日导致CI失败。此前CR052—056“后端接缝待办”已由本修复完成。
云端已上线quant-mvp-backend:cr057，镜像sha256:4a1f05bea8712d9b32fa227beda8710cb59ecba9be77cf52337349c6f029f1c0；日更执行器image-id同步新镜像，07:30 continuous规则不变。后端/网关healthy，维护标记已移除；timer active/enabled，实查下一2026-09-27 07:30 CST。备份在/opt/intelligent-quant-cr057-20260926/backup，保留旧cr050镜像与配置供回滚。
85文件源码包SHA256 5e5bdddad92a7fe8a240656b0f04948734c1b332ed7db4dc14b9ee1b297b9073，不含权重、私有数据库、真实行情缓存。禁网候选五模块、六策略回测通过（传统各65净值点、四RL各62点），新日历/只读训练检查通过。首次候选验收脚本90日起点进入训练期被正确拒绝，按模型实际outOfSampleStartDate修正脚本后通过，不放宽门禁。
维护排空后SQLite备份实际恢复：111条旧任务，切换前后逻辑SHA256 424d8b373b72445b2abbb2ef43905f1d79fbe720b17aefd92ec2814a88e9d329一致、integrity ok。行情指针e434f02c8f5530c133f22df60441cafa5d8fc3d220f4e14a6a18c7f56eedc7d5及两份日更账本哈希不变；禁网dry-run返回waiting_new_day/targetDate=2026-09-24，没有触发采集。现有四个已发布实验模型保持原样，研究深历史权重未替换线上模型；不能将代码部署描述成长窗口权重已发布或收益研究已完成。
Pages最新成功发布为7320702，工作流35685924282；git diff确认该版本与main的apps/frontend、package.json、package-lock.json、Pages工作流及API配置检查脚本全部无差异。本次PR没有前端路径改动，未触发新Pages构建，也无需为无差异前端重复发布。现有Pages实际连接新云后端已验证。
Edge实际访问https://why621.github.io/intelligent-quant-analysis-platform/：327 ready、行情截至09-24、六策略排行、ETF相关性64样本、模拟配置依据09-24，同版校验通过；点选511260/512010后相关性HTTP200，1440/390视口截图完成，手机无横向溢出，无pageerror。通过Pages来源提交的一次DQN+510300基准异步回测b4dcb764-d449-44a8-9f81-d472a9f091e8成功，新增验收任务与此前111条保留检查分开统计。GET /strategies出现一次传输失败，限定重试后成功；POST不自动重试，网络偶发根因仍未确定。初轮浏览器脚本因行业分类新复选框导致选择器不唯一，缩小至.asset-option后通过，失败记录保留。
证据与命令：artifacts/cr057-deploy-20260926下archive.json、prepare.log、validate.sh.log、validate-r2.sh.log、cutover.sh.log、final-check.log、pages-release.json及pages-r2/pages-verification.json/截图；远端stage保存validation.json/deployment.json。执行源码包校验、docker build --network none、禁网只读候选、cutover.sh、Edge pages-r2.cjs、systemctl show及只读Docker健康检查。没有更改定时器或执行本地/云行情回填。
用户于09-22确认连续两日更新已人工验收完成，该结论来源为负责人确认，不冒充本轮重新读取了两日完整调度证据。旧Codex 300-mvp监控已要求删除，但本会话仍无管理工具，不能宣称已删除；云端07:30日更与该监控相互独立。
本轮按用户“已合并回写文档”及后续部署指令回写；用户进一步明确授权将文档推送GitHub；同步分支为codex/pr39-deploy-20260926，主分支待文档PR合并。代码与云部署已完成，不需要再次合并PR39。剩余：多资产/多种子长窗口绩效及长期收益研究、深市/ETF官方事件自动源、网络偶发故障定位等不因本次部署记为完成。
