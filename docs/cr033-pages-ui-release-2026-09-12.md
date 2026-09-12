# CR-033 新UI Pages发布（2026-09-12）

用户授权CR032新UI更新Pages。候选包括赛博视觉、资产搜索/类型筛选/复选/标签及策略说明卡，API口径不变。只提交前端、新UI验证工具与CR032/033报告，其余未提交云运维修改保留原工作区。

CR032已有57前端测试、本地真实327快照Edge交互及回测通过。生产候选使用VITE_API_BASE_URL=https://43.161.223.91/api和base=/intelligent-quant-analysis-platform/构建成功，位于artifacts/cr033-pages-20260912/dist，主JS index-CCs2woci.js、CSS index-C4OTcnWm.css。读取云数据而非本地09-09快照，不重采或修改云端。

远端main=53db31211ff21387e6dccd303ae19d652bd74dd4；deploy-pages.yml在main前端变更合并后构建部署，默认HTTPS云API及配置检查已存在。main要求PR，不绕过保护。环境无gh和GitHub API令牌，因此准备codex/cyber-ui-cr033分支，需有权限用户创建/合并PR。分支上传不等于Pages已发布。

合并后需核验Pages工作流成功、线上新UI与云09-11版本，以及配置请求200，再回写最终结果。源码不含真实行情/数据库/密钥。新UI验证脚本原生点选定位不同于旧select脚本，不直接将本地脚本结果冒充公网验收。


CR-033推送结果（2026-09-12）：新UI提交008ecb8f667552cca658e0679e21c99031fd0dbf已成功上传origin/codex/cyber-ui-cr033，包含9个明确的UI/验证/报告文件；57前端测试与生产构建、HTTPS URL检查、差异检查通过。API固定https://43.161.223.91/api，生产资源index-CCs2woci.js/index-C4OTcnWm.css。尚未创建/合并PR，无新Pages工作流完成证据，因此线上UI未认定更新。当前环境没有gh/GitHub API令牌，需用户按保护规则创建/合并：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/cyber-ui-cr033 。之后核对真实新UI及配置200再完成发布验收。审批通信中断的操作未执行，复核后重试成功，不是GitHub拒绝发布。其他云运维未提交修改保留；此段最终结果先回写本地，CR032/033候选报告已随UI分支上传。

## CR-034 PR21离线CI日期修复（2026-09-12）

截图失败已本地复现2项：test_overview_failure_does_not_mark_history_failed的行情用date.today()，周六为09-12，但生产latest_session预期09-11，故history=stale。不是新UI或线上采集失败。

仅修改services/algorithms/tests/test_overview_resilience.py，冻结provider._today并显式提供行情日；参数覆盖周五、周六、周日，以及周六只到周四必须stale的反例，分别结合有/无概览缓存。保留历史和概览独立状态、failedSymbols、CLI降级退出码断言；不改生产数据或降低检查。

本地复验该文件15项通过；与CI同范围命令（设置PYTHONPATH=services/algorithms/src:services/backend/src）`.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -m 'not network' -q -o addopts=`：323 passed, 8 deselected in 14.25s。git diff --check通过。接着推送同一PR21分支，GitHub整条容器smoke/前端检查结果需另核实，不以本地离线通过代替远端全CI或Pages发布。
