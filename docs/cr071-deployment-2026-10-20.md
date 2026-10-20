# CR071 发布记录（2026-10-20）

用户当次授权“推送部署线上”。保留全部旧模型，发布独立训练的增强PPO和增强TD3；没有重新训练、购买算力或修改行情。云端已完成切换，公网浏览器验收已完成，PR #56已合并，Pages独立验收完成；最新证据见文末。

## 发布身份

- 源码：`75843a22c36dc4ca11a8ba4e47d5d7e30056a03b`，分支`codex/cr071-masked-ppo-td3`。
- 云镜像：`sha256:1813175e4d3ed0def468192a8a0f8deaa709471273d76fcbf01cd1773951dcb8`，标签`quant-mvp-backend:cr071-r1`。
- 暂存及备份：`/opt/intelligent-quant-cr071-20261020-r1`及`backup/`。
- PPO bundleHash：`3f8c136c29d528f7f56d552ea6ead7b98601c2aa50bb083f8a684f2e86f2adf2`。
- TD3 bundleHash：`82fddd08fb471e2f3837b102d0d5857e06a183a00f449c0fd14d424dfa5fa5dd`。
- 契约0.15.0，12策略、六联合组合模型、8项当前配置排行；旧GET 510300六项评价保留兼容。

## 云端隔离验收与切换

`python tools/deploy_cr071_release.py package|upload|build|validate|cutover --output artifacts/cr071-deploy-01`逐步执行。候选容器断网、输入只读、临时DB，使用真实业务日期及当前发布行情（截至2026-10-19），未注入历史时钟。

33次成功回测、12次模拟、8项当前配置排行及40项负向检查通过；覆盖全部六组合的2/10资产、反序、独立现金账本、费用、现金比例、已证实停牌及未知缺口拒绝，旧单资产模型兼容和CR067日更依赖隔离。601059存在当前未知行情缺口，六组合均明确异步失败且result=null，不冒充327只在任意区间全部可计算。

持日更锁、维护门、排空任务后完成SQLite备份及真实还原验证，原152任务逻辑SHA256为`d13376f7a13b18d15116da092d92d9c7d23ec328e5dcaf240544a30e4a0cf335`，切换后完全一致。原四联合模型bundle哈希及四单资产模型文件均保持。上线实际8项排行与隔离候选结果逐项一致，耗时2.548秒。回滚未触发。

行情指针`2737973e43de46198e139599e11be370dcf6fee9bdf323d85b03e7beb57b5445`、日更脚本/镜像/账本及07:30定时器配置均保持；timer active，dry-run waiting_new_day。这不等于下一次自动日更已成功。

## 原始证据与边界

Ignored目录`artifacts/cr071-deploy-01`保存打包哈希、cloud-before.json、cloud-build.txt、cloud-validate.txt、cloud-cutover.txt及浏览器证据；模型/真实行情/数据库不推入Git。

打包脚本首次静态检查发现旧代码残留，修复后通过；本地打包两次字段检查失败后按真实manifest.algo修正，只有最终75843a2包被上传。第一次上传申请因审批服务连接中断未执行，正常重试审批成功。上述均未触发生产变更或重训。

性能边界沿用训练记录：PPO和TD3历史测试平均收益分别-3.2024%/-3.1631%，TD3验证组间差异大；执行可用不代表收益改善，也不是论文完整复刻。[独立训练与本地验证](cr071-masked-ppo-td3-2026-10-20.md)。

## 云站公网验收完成

最终真实Edge验收84项通过、36个API响应成功、0页面运行错误。涵盖增强PPO十资产回测、8项排行与回测指标/费用严格一致、费用/现金/日期/资产变化失效重算、排行榜加载增强TD3再回测、模拟参数同步、1440/390/320布局、动态效果/光标偏好与减少动态设置。

原152任务逐行保持，仅新增增强PPO/TD3两条成功验收任务，总154。验收任务：62d42689-ec25-463a-9f7c-3bb01c7c4a88, ca18b1f4-2eb7-4c04-a8b0-0f93376af47a。重试全部恢复这两条任务，不重复创建。模拟为只读计算，因窄屏定位与复验共执行4次并保存在online-mutations.json历史中。

首次模拟结果在320px溢出375px。第一次仅加说明换行后仍为363px；最初“长模型标识”归因不充分，进一步确认原始持仓百分比有17位小数/科学计数法撑开auto网格列。最终沿用plainPct格式化现金及资产百分比，并使用可收缩网格列，保留全文且不改变API/算法精度。静态补丁源码361e3a2，分别备份在云stage/web-patch-01和02，未重启后端。第二版完整真实模拟状态通过320px检查；只恢复任务、没有模拟结果的第一次重试不作为该修复证据。

前端118项测试再次通过；云站与Pages各632模块构建。失败报告及截图以before-webfix/after-first-webfix命名保留，最终报告与日志位于ignored artifacts/cr071-deploy-01。

复现：`node tools/verify_cr071_browser.cjs https://43.161.223.91/ artifacts/cr071-deploy-01/browser`（复用任务与模拟证据）；`python tools/verify_cr071_deployment.py --output artifacts/cr071-deploy-01`。正式Pages需要main合并触发，再用同一浏览器工具对Pages网址单独验收；此刻尚未宣称Pages新版静态文件已发布。

最终只读发布审计通过：12个公网文件SHA256与最终dist-cloud全部匹配，服务healthy；原152任务逐行保持，总154，仅两条已记录验收任务。旧模型、行情指针、日更脚本/镜像/账本及07:30定时器保持。原始证据：artifacts/cr071-deploy-01/cloud-final-audit.json。

### CR071 GitHub Pages最终验收完成（2026-10-20）
PR #56已合并，main提交71d4a9fe3f6c533e76373eb26a539b8c533fc7c8；Pages工作流39398887382 completed/success。真实Pages Edge检查84项通过、37个API响应成功、0页面运行错误；12个公网文件SHA256均与最终dist-pages一致，入口index-CeR_RXab.js。增强PPO/TD3可选择并恢复真实十资产结果，八项当前配置排行与回测指标/费用一致，费用/现金/日期/资产变化失效重算、排行加载、模拟表单联动和1440/390/320布局、动态偏好检查通过。
本次复用云站两条任务及已记录模拟结果，没有新增任务或重复模拟计算。模拟结果实际渲染后的窄屏修复证据来自上一轮云站最终完整验收，不能说本次Pages重新计算/渲染了模拟结果。原152任务逐行保持，总154；镜像healthy，旧模型、行情指针、日更脚本/镜像/账本及07:30定时器保持。
命令：`node tools/verify_cr071_browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/ artifacts/cr071-deploy-01/browser`。Python整合终验在公网文件下载阶段等待，未声称该完整命令成功；改为单独执行原脚本全部服务器保留断言，并用真实Edge fetch及Web Crypto SHA256核对同一12文件，标准不变；原等待进程已停止。这是本机下载链路等待，不是网站故障证据。
证据（ignored）：artifacts/cr071-deploy-01/browser/online-pages-browser.json、pages-preservation-audit.json、pages-browser-file-hashes.json；文件检查复现：`node artifacts/cr071-deploy-01/verify-pages-hashes.cjs`。
T-CR071-8功能代码推送、main合并、Pages发布及独立验收完成。最终证据文档同步codex/cr071-pages-evidence，该文档分支是否合并不影响已上线功能。无重训/云镜像重部署/行情改写。收益有效性仍未证明，601059未知缺口限制保持。
