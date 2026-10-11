# CR065：EarnMore 调研与联合组合研究实现

日期：2026-10-11。范围：原始论文/官方代码只读核查、本地实现及离线验证；不代表正式训练、绩效验收或线上发布。用户确认资产名单未定，允许本地小规模试训，正式训练和发布另行确认。

## 1. 当前实现为什么需要改变

CR062 版本的 `BacktestEngine.run` 将初始资金等分，再逐只资产独立运行，最后合并净值；`TradingEnv` 的动作是单个目标仓位，观察只有一只资产特征及其仓位。该方式可以比较独立策略，但不能让同一时刻的十只资产共同竞争一笔资金，不能称为联合组合优化。现有四个已发布 510300 权重继续保留，其输入维度和训练语义不能转换为新组合权重。

## 2. 原始来源与可借鉴内容

EarnMore 为 WWW 2024 论文《Reinforcement Learning with Maskable Stock Representation for Portfolio Management in Customizable Stock Pools》。模型在训练全局池 GSP 上学习，将不同股票数量、不同组成的子池 CSP 表示为随机掩码后的联合状态；使用掩码重建和 SAC 优化，输出资产及现金权重。CSP 是 GSP 子集，论文不证明任意未见股票都具备零样本有效性。[论文原文，第 3–4 节](https://arxiv.org/html/2311.10801v2)

官方配置的状态是 `num_stocks × days × features`，动作是 `num_stocks + 1`，含现金。DJ30 示例用 28 只资产，掩码比例范围 0.6–0.8；这些是其特定实验参数，不应直接当作本项目十资产的最佳参数。[官方配置](https://github.com/DVampire/EarnMore/blob/main/configs/mask_sac_portfolio_management.py)

官方表示网络编码可见资产，并使用可学习 mask token 恢复掩码位置，重建损失针对被掩码的部分。[表示网络](https://github.com/DVampire/EarnMore/blob/main/pm/net/mask_time_state.py)

官方 SAC 实现把 mask 和 ids_restore 保存到 replay 中，另设掩码资产分配惩罚。低温 softmax 和软惩罚不能替代平台所需的严格零权重约束。[SAC 实现](https://github.com/DVampire/EarnMore/blob/main/pm/agent/sac/mask_sac.py)

**未直接复制官方交易环境。**所查 `EnvironmentPV.step` 使用相邻收盘收益，`transaction_cost_pct` 虽被接收，但该函数内没有扣除交易成本。本项目继续执行 t 收盘决策、t+1 开盘实际扣费的规则。[官方环境](https://github.com/DVampire/EarnMore/blob/main/pm/environment/pm_based_portfolio_value.py)

上述来源于本轮网络只读查询，借鉴机制不等于复现论文收益。

## 3. 本地最小实现

- `rl/portfolio_features.py`：最多十个资产槽位，每槽十四个因果市场特征、实际仓位和有效掩码，末尾为现金比例；观察共 161 维。动作十一维，前十维为资产、最后一维为现金。硬掩码后归一化，全零动作明确表示全现金。
- `rl/portfolio_env.py`：无 Gym 依赖的 `PortfolioEpisode` 与延迟创建的 Gym 包装。所有资产共享唯一现金及持仓向量，调用公共 `portfolio/execution.py`，没有独立子账户。奖励为实际扣费后的组合对数收益，滑点在成交价中体现，不重复扣除。
- 训练每回合抽取 2–10 个同时参与的资产，随机槽位顺序及训练窗口；池在回合内不变。时间分区先于采样，数据缺失、日期不一致直接拒绝，不静默删资产、压缩日期或填 OHLCV。
- `rl/portfolio_policy.py`：组合模型专用 manifest、哈希校验、加载及联合推理。记录训练池、每资产训练数据哈希、时间分区、费用、观察/动作/执行版本。服务式推理拒绝训练/验证区间、池外资产、不同成本和旧单资产 bundle。
- `rl/portfolio_train.py`：仅本地 CSV/显式 DataFrame 输入；PPO/SAC/TD3，CPU 单进程单线程，有界步数和时间。成功必须实际优化更新、保存、重新加载并联合推理，保存验证记录。输出目录不可覆盖。
- `research_backtest` 提供本地留出区间联合回放；可使用训练期之前的历史作因果预热，但第一个评价决策必须晚于训练及验证截止日，不能默默推迟请求窗口。

这是一种轻量联合输入加掩码的 MLP 基线，**未实现完整 EarnMore 自监督重建，不声称天然置换等变或资产池外泛化**。推理按资产代码排序保证调用方顺序一致；随机槽位训练是数据增强，不能替代网络等变性证明。

PPO/SAC/TD3 支持连续 Box；SB3 DQN 不支持连续 Box，也不支持 MultiDiscrete。DQN 继续保留旧单资产模式，未把十个独立离散模型拼接为组合模型。[SB3 算法支持表](https://stable-baselines3.readthedocs.io/en/master/guide/algos.html)、[DQN 文档](https://stable-baselines3.readthedocs.io/en/master/modules/dqn.html)

## 4. 本地调用与证据边界

```text
quant-portfolio-smoke --data-dir /明确的本地CSV目录 \
  --symbols 资产代码1,资产代码2,资产代码3 \
  --asset-types-json /明确的资产类型映射.json \
  --train-start YYYY-MM-DD --train-end YYYY-MM-DD \
  --val-start YYYY-MM-DD --val-end YYYY-MM-DD \
  --test-start YYYY-MM-DD --test-end YYYY-MM-DD \
  --output-root /不入Git的组合试训目录 --run-id 新的运行ID \
  --algo ppo --steps 2048 --max-seconds 180 --episode-bars 64 \
  --stamp-duty-mode asset_date
```

以上为参数模板，日期及标的需来自实际缓存覆盖。每个 CSV 名为 `SYMBOL.csv`，包含 date/open/high/low/close；资产类型映射明确使用 stock 或 etf。训练至少保留 140 根预热及完整回合数据。CLI 不下载、不回写行情，不连接云端或替换发布权重。

本地限制为请求 64–10000 步、1–600 秒，默认 2048 步和 180 秒。PPO 按完整 rollout 更新，实际步数可能超过请求下限，manifest 同时记录请求步数、实际步数和优化次数。若时间预算结束时尚未发生优化，不保存为已训练模型。验证/测试日期仅为登记的隔离窗口；小试训不使用它们选优，manifest 明确 validationExecuted=false/testExecuted=false。

验收包含：A 仓卖出资金可买 B、资金守恒、次日开盘成交、费用与滑点拆分、环境和公共执行器逐笔一致、2/3/10 资产掩码、资产重排执行等价、未来行情不影响过去特征、分区先于采样、旧 bundle/池外/样本内/费用不符拒绝。无 ML 离线测试与实际 learn/save/load 验证分开记录；合成行情只用来验证机制，不当作收益证据。

## 5. 本模块验证回写

2026-10-11，在 `services/algorithms` 下运行：

```text
<原仓库 .venv/bin/python> -m pytest tests/test_portfolio_rl.py
# 26 passed, 3 skipped（WSL 环境无可选 Gym/SB3，三项实际学习测试明确跳过）

<原仓库 .venv/bin/python> -m ruff check \
  src/quant_platform/rl/portfolio_features.py src/quant_platform/rl/portfolio_env.py \
  src/quant_platform/rl/portfolio_policy.py src/quant_platform/rl/portfolio_train.py \
  tests/test_portfolio_rl.py
# All checks passed!
```

另复用已有 Windows Python 3.13、Torch 2.8.0+cpu 和原仓库 `artifacts/cr062-python-deps` 中 Gymnasium 1.3.0 / SB3 2.9.0，不安装依赖，执行同一测试文件的 `-m rl` 三个参数化用例：**3 项通过**。PPO/SAC/TD3 均实际学习 128 步，分别记录 3/24/24 次优化更新，随后保存、校验、重新加载并输出十一维联合动作。该三项使用**合成行情**，仅验证学习链路。测试临时证据位于原仓库 ignored `artifacts/cr065-rl-unit-3d97e53a9dc6496ca4d0e6b34d80006d/`，没有修改已发布权重。

Windows pytest 首次运行因默认沙箱临时目录不可写，在测试 setup 阶段失败，尚未训练；改用工作区内全新唯一 `--basetemp` 后通过。WSL 首轮有一项测试期望了错误的异常类型，修正为实际 `RLInsufficientHistory`，另补了“总条数足够但请求日前预热不足”反例后重跑通过；没有删除有效检查。

真实缓存试训、全模块联调及发布状态由 CR065 主验收记录另列。本节不把合成验证替代真实数据训练，也不把 128 步冒烟训练写成收益或泛化能力证明。
