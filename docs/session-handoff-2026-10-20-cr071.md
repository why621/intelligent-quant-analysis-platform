# CR071交接：增强PPO/TD3云端与Pages均已发布并验收

用户最新指令：保留可用的原三个联合组合模型，新增增强PPO后再新增增强TD3，分别训练并验收。早先下架要求撤销；未下架任何模型。旧组合本来就共享账户，不是早期独立账户拼接。

当前开发分支`codex/cr071-masked-ppo-td3`，基于CR070 Pages验收文档提交8f8fe6e；功能代码已合并PR #56，最终文档同步独立证据分支，见下方发布回写。活动工作树为根目录`artifacts/cr065-worktree`，原根工作区已有用户改动未触碰。用户随后明确授权“推送部署线上”，已完成CR071云端隔离验收及切换。

已完成：

- PPO新鲜轨迹/裁剪目标/GAE、TD3双Q/延迟策略头/目标平滑，复用共享注意力、掩码重建、随机子池及回合内换池；独立架构、独立权重、各65536决策步。
- PPO先完成训练与327资产40组验收，再训练并验收TD3。正式候选分别为cr071-masked-ppo-s42与cr071-masked-td3-s42，参数、哈希和亏损结果见[详细记录](cr071-masked-ppo-td3-2026-10-20.md)。
- 原模型全部保留；新增portfolio_masked_ppo/portfolio_masked_td3，OpenAPI0.15.0、六组合目录上限、安全加载白名单及原发布门禁保持。
- 本地回归688通过/26跳过/16网络排除，前端118通过；真实接口20回测/12模拟/8项排行/5种配置、27项真实Edge检查通过。
- 基准按代码排序归约，修复反序请求Alpha/Beta约1e-14浮点差异；先复现失败，再保持原严格检查通过。

重要边界：

- 本地冻结行情截至2026-09-09，模拟验收显式使用2026-09-10历史日期；不是当前行情可用性或云验收。
- 两模型历史测试均亏损，TD3验证各组差异大，不能称更稳定盈利或优于旧版；历史测试不是全新盲测。
- PPO训练后首次导出遇到WSL路径权限，已从哈希校验后的保存权重恢复导出，不重训；新增--export-only严格核对原计划。
- 首次本地浏览器服务SQLite WAL共享路径锁失败，改用Windows原生临时DB；生产逻辑未改。最终服务已由stop文件正常关闭。
- Ruff可执行在根`.venv/lib/python3.12/site-packages/bin/ruff`，不是`.venv/bin/ruff`。Windows Torch原生依赖已存在，额外pure Python/Windows依赖取兄弟cr062-python-deps、cr066-python-deps。无需安装或重新训练。

证据均ignored：

- `artifacts/cr071-ppo-production-01`与`cr071-td3-production-01`：冻结计划、训练、模型及全目录评估。
- `artifacts/cr071-local-01/02`保留失败，`cr071-local-03/report.json`为成功真实接口结果；其models/release.json合并全部六个组合模型。
- `artifacts/cr071-browser-01`真实页面结果及截图；`cr071-browser-server-02`保存本机临时DB位置与stop标记。
- `artifacts/cr071-regression.xml`和WSL `/tmp/cr071-regression-final.txt`、`/tmp/cr071-frontend.txt`。

发布脚本已适配六组合，云端33回测/12模拟/8排行/40负向及日更隔离通过，原152任务备份切换后完整保持。真实云站验收发现模拟权重长浮点字符串的窄屏溢出，补丁及复验状态见[发布记录](cr071-deployment-2026-10-20.md)。main受保护，当前无GitHub API合并授权，需推送后由用户合并PR再单独验Pages。

### CR071云站发布回写（2026-10-20）
云端CR071已上线：增强PPO/TD3独立权重加入，全部旧模型保留；12策略、六组合、8项当前配置排行。云隔离33回测/12模拟/40负向、日更隔离通过；真实云站84项浏览器检查、36个API成功响应、0运行错误。修复模拟持仓长浮点比例的320px溢出，前端118测试与两套构建通过。T-CR071-6/7完成，T-CR071-8推送及Pages合并验收待后续。训练历史亏损与未证明收益改善继续披露。详见docs/cr071-deployment-2026-10-20.md。

最终只读发布审计通过：12个公网文件SHA256与最终dist-cloud全部匹配，服务healthy；原152任务逐行保持，总154，仅两条已记录验收任务。旧模型、行情指针、日更脚本/镜像/账本及07:30定时器保持。原始证据：artifacts/cr071-deploy-01/cloud-final-audit.json。

### CR071 GitHub Pages最终验收完成（2026-10-20）
PR #56已合并，main提交71d4a9fe3f6c533e76373eb26a539b8c533fc7c8；Pages工作流39398887382 completed/success。真实Pages Edge检查84项通过、37个API响应成功、0页面运行错误；12个公网文件SHA256均与最终dist-pages一致，入口index-CeR_RXab.js。增强PPO/TD3可选择并恢复真实十资产结果，八项当前配置排行与回测指标/费用一致，费用/现金/日期/资产变化失效重算、排行加载、模拟表单联动和1440/390/320布局、动态偏好检查通过。
本次复用云站两条任务及已记录模拟结果，没有新增任务或重复模拟计算。模拟结果实际渲染后的窄屏修复证据来自上一轮云站最终完整验收，不能说本次Pages重新计算/渲染了模拟结果。原152任务逐行保持，总154；镜像healthy，旧模型、行情指针、日更脚本/镜像/账本及07:30定时器保持。
命令：`node tools/verify_cr071_browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/ artifacts/cr071-deploy-01/browser`。Python整合终验在公网文件下载阶段等待，未声称该完整命令成功；改为单独执行原脚本全部服务器保留断言，并用真实Edge fetch及Web Crypto SHA256核对同一12文件，标准不变；原等待进程已停止。这是本机下载链路等待，不是网站故障证据。
证据（ignored）：artifacts/cr071-deploy-01/browser/online-pages-browser.json、pages-preservation-audit.json、pages-browser-file-hashes.json；文件检查复现：`node artifacts/cr071-deploy-01/verify-pages-hashes.cjs`。
T-CR071-8功能代码推送、main合并、Pages发布及独立验收完成。最终证据文档同步codex/cr071-pages-evidence，该文档分支是否合并不影响已上线功能。无重训/云镜像重部署/行情改写。收益有效性仍未证明，601059未知缺口限制保持。
