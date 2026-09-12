# CR-033 新UI Pages发布（2026-09-12）

用户授权CR032新UI更新Pages。候选包括赛博视觉、资产搜索/类型筛选/复选/标签及策略说明卡，API口径不变。只提交前端、新UI验证工具与CR032/033报告，其余未提交云运维修改保留原工作区。

CR032已有57前端测试、本地真实327快照Edge交互及回测通过。生产候选使用VITE_API_BASE_URL=https://43.161.223.91/api和base=/intelligent-quant-analysis-platform/构建成功，位于artifacts/cr033-pages-20260912/dist，主JS index-CCs2woci.js、CSS index-C4OTcnWm.css。读取云数据而非本地09-09快照，不重采或修改云端。

远端main=53db31211ff21387e6dccd303ae19d652bd74dd4；deploy-pages.yml在main前端变更合并后构建部署，默认HTTPS云API及配置检查已存在。main要求PR，不绕过保护。环境无gh和GitHub API令牌，因此准备codex/cyber-ui-cr033分支，需有权限用户创建/合并PR。分支上传不等于Pages已发布。

合并后需核验Pages工作流成功、线上新UI与云09-11版本，以及配置请求200，再回写最终结果。源码不含真实行情/数据库/密钥。新UI验证脚本原生点选定位不同于旧select脚本，不直接将本地脚本结果冒充公网验收。
