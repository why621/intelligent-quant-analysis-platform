# CR071交接：增强PPO/TD3本地验收完成，未推送或发布

用户最新指令：保留可用的原三个联合组合模型，新增增强PPO后再新增增强TD3，分别训练并验收。早先下架要求撤销；未下架任何模型。旧组合本来就共享账户，不是早期独立账户拼接。

当前开发分支`codex/cr071-masked-ppo-td3`，基于CR070 Pages验收文档提交8f8fe6e；本轮代码与文档尚未提交/推送。活动工作树为根目录`artifacts/cr065-worktree`，原根工作区已有用户改动未触碰。线上仍为CR070；没有当次发布授权。

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

下一步只有用户当次授权推送/发布后才执行。需适配CR071六组合模型云端候选/发布脚本、使用当前线上行情进行隔离回归，备份及保留现有模型/任务/日更，再单独验证云站和Pages。不能直接拿写死CR070四组合模型数量的云验收脚本宣称通过，也不能用本地历史模拟代替线上验收。
