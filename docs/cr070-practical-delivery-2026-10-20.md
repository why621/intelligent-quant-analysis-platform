# CR070 实用增强：本地交付与验收

2026-10-20。按用户最新要求，**只吸收论文中可利用的优化点，不完整复刻EarnMore**。本次范围的实现与本地验收完成；没有推送或发布。此前5–8工作日/2–3周估算针对更广研究范围，已被本次范围收敛替代，不再作为当前开发计划。

## 本次采用的机制

| 机制 | 实现与证据 | 边界 |
| --- | --- | --- |
| 共享资产表示、跨资产注意力 | 无股票ID/槽位位置编码进入策略，真实网络置换等变测试 | 当前因果14特征，非论文完整时序编码 |
| 可变资产池与动作屏蔽 | 训练池随机抽2–10资产，单一共享资金与费用；未选槽位硬屏蔽 | 每只资产仍需真实行情与预热 |
| 掩码重建辅助学习 | 隐藏目标输入、训练专用解码查询、独立辅助编码器学习率，可关闭辅助编码器更新或使用无重建路线 | 目前对照未证明交易收益增益，不能作为宣传结论 |
| 回合内换池 | 次日清算退出资产、保留数量、停牌整体延期、按代码重排、现金/费用连续 | 显式换池日无主动新池买入，下一策略日才买入 |
| 换池训练接入 | 独立随机流、可配置间隔、延期请求保留/重试，记录事件与实际市场步 | 研究训练器，不是生产模型目录 |
| 可复现检查 | 保存加载、数据/时间隔离、训练预算、方案哈希、同seed轨迹/权重一致 | 小试训不等于收益验收 |
| 页面入口说明 | 清楚区分旧510300单资产模型与组合模型 | 本地完成，尚未部署 |

## 换池训练的具体实现

`train_masked(..., pool_switch_interval=N)`在每N个回合内策略决策后请求一个随机2–10资产池。默认0沿用原训练行为。随机换池流独立于重放采样，不改动未启用换池的随机流。命令行也提供`--pool-switch-interval`。

一次策略步骤后若发生换池，旧收盘至策略执行后收盘奖励为r1，随后换池日奖励为r2。它们合并为一个经验：

```text
reward = r1 + 0.99 × r2
bootstrap_discount = 0.99²
next_observation = 换池执行或延期后的收盘状态
```

无换池步骤仍使用原来的0.99折扣。终止标记来自最后实际市场步骤，终止后不bootstrap。重建优化不依赖虚构换池动作；没有为外部事件构造一个新模型动作。奖励累计只供学习，不能把折扣累计奖励当作账户实际区间收益；账户仍保存真实净值与成本。

延期请求在下次策略步骤后重试，回合终止则清除；不中断正常持仓估值。元数据记录`poolSwitchInterval`、`marketSteps`、`poolEventCount`、最多256条`poolEvents`和`stepBudgetUnit=policy_decisions`。启用换池后“256策略步”可能多于256市场步，做等预算对照必须明确比较单位。本轮不拿新运行与旧固定市场步结果作收益比较。

## 当日验收

| 检查 | 本轮实际结果 |
| --- | --- |
| Windows Torch掩码、换池、选择协议专项 | 37通过，9.71秒 |
| WSL算法、后端、资产池工具离线回归 | 685通过、24可选依赖跳过、16网络测试排除，31.45秒 |
| 前端单元测试 | 117通过 |
| 前端生产构建 | 632模块，成功 |
| CR070全部新增Python代码Ruff | 通过 |
| git diff --check | 通过 |
| 现有真实数据换池小试训 | 32资产，256策略步、225优化、315市场步、59换池 |

专项37项含11项换池执行测试、24项Torch机制测试、2项选择协议测试。它与全量离线回归包含重叠测试，不能直接相加当作独立用例数。专项新增核对两日奖励/折扣的实际Critic目标值、禁止错误广播、同seed换池训练权重/事件完全一致及保存配置。算法环境仍有3项旧可选SB3用例跳过，整体24项跳过包含缺少Torch/SB3的用例；Windows专项补充本次Torch路径，但不冒充旧SB3全部已运行。

真实小试训预先冻结方案，采用原训练池24只股票、8只ETF，训练日期截至原trainEndDate，未评价验证/测试收益、未载入留出资产。59次换池来自这一真实行情运行；停牌延期由合成机制测试覆盖，不能把这59次换池当作真实停牌验证。模型仍标记research、releaseEligible=false，未注册为线上模型。

复现命令（工作树内，使用已有依赖，设置对应PYTHONPATH）：

```text
python tools/smoke_changing_pool.py --experiment ../cr069-universe/experiment --output artifacts/cr070-switch-smoke-01
pytest services/algorithms/tests/test_masked_portfolio.py services/algorithms/tests/test_changing_pool.py tools/test_masked_comparison.py -o addopts= -q
PYTHONPATH=services/algorithms/src:services/backend/src:. ../../.venv/bin/python -m pytest -c services/algorithms/pyproject.toml services/algorithms/tests services/backend/tests tools/test_universe_experiment.py --disable-warnings --maxfail=3 -rA
npm --prefix apps/frontend test
npm --prefix apps/frontend run build
git diff --check
```

真实实验输出目录已存在，重现需使用新目录。Windows专项先载入Torch/Pandas，再将根目录`.venv/lib/python3.12/site-packages`加入sys.path以复用pytest，设置PYTEST_DISABLE_PLUGIN_AUTOLOAD=1。原始冻结方案、模型与报告位于ignored `artifacts/cr070-switch-smoke-01`，不提交真实行情或模型权重。

## 完成的含义与后续

本次“借鉴机制”的本地交付已完成，不再以完整时序MAE、复现论文所有算法或证明长期超额收益作为完成条件。此前三路线、多seed及辅助更新实验仍保留，包括掩码路线没有胜出的结果。重建功能可用与重建能提高收益是不同结论。

生产模型接入、正式候选训练、模型登记、云端/Pages验收和发布仍未完成，不是今天已经上线。当前服务继续使用CR069；后续若要求上线，需要单独登记适配独立研究权重、生产证据和发布流程，不能直接将256步小试训权重冒充正式模型。日更未改动。
