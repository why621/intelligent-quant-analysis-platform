# CR070：掩码表示学习与可变股票池，第一阶段

后续阶段及用户收敛后的最新范围，见[2026-10-20实用增强本地交付](cr070-practical-delivery-2026-10-20.md)。以下为第一阶段历史证据，不代表所有后续任务仍待开发。

日期：2026-10-20。当前状态：**本地研究链路实现并验证；未正式训练、未推送、未上线，不能替代CR069线上模型。**

## 需求与阶段

用户在核查旧单资产PPO截图后明确要求，按此前规划进一步实现EarnMore掩码表示学习与更强的可变股票池适应能力。本阶段完成共享表示、重建辅助任务、SAC、真实数据小试训、样本外研究回放和入口说明。沿用共享账户、次日开盘成交及实际费用。旧四单资产和三个CR069组合模型保持。

| 阶段 | 状态 |
| --- | --- |
| 区分旧单资产与多资产入口 | 本地文案及测试完成，尚未部署 |
| 注意力表示、掩码重建、SAC训练/推理/保存加载 | 本地完成 |
| 置换等变、屏蔽、无未来数据泄漏、参数更新 | 合成机制测试通过 |
| 真实数据小试训、留出资产/未来时段执行 | 完成，不是绩效验收 |
| 匹配数据/预算的MLP对照、无重建消融、多种子正式训练 | 待下一阶段，不能据本轮结果声称更强收益泛化 |
| 回合中途增删股票、退出清算/停牌处理 | 待单独实现及验证；当前仅回合重置时换池 |
| 生产模型契约、模型目录、云端与Pages发布 | 未实施；HTTP OpenAPI仍0.13.0，正式训练及发布另行确认 |

## 与EarnMore的对应和差异

来源：[EarnMore原论文第3–4节](https://arxiv.org/html/2311.10801v2)。借鉴随机股票池、掩码表示/重建、SAC和资产权重约束，不声称论文完整复现或论文收益复现。

- 当前输入继续使用14个因果市场特征、实际持仓和现金比例，没有新增论文的原始时序卷积编码器。
- SetEncoder对资产采用同一投影和跨资产注意力；无固定槽位位置编码。现金使用独立全局token，Actor逐资产共享，Critic对有效资产聚合。置换等变测试直接打乱输入张量和动作，不依赖推理前按代码排序。
- 辅助训练随机遮蔽部分真实资产特征，仅从可见资产编码和训练专用资产ID查询重建被遮蔽的因果特征。可学习mask token、解码器和MSE损失只用于辅助训练；隐藏值在投影前清零，且不能成为注意力键值。资产ID不进入Actor/Critic，因此不限制推理只能使用训练ID。
- 此适配重建的是特征，不是论文原始价格时序；不是全327个固定身份位置的GSP网络。推理仍最多十个有效位置，以有效掩码条件化策略，不将“支持2–10资产”宣传成无限维度支持。
- Actor输出sigmoid-Gaussian连续得分，使用其正确变换密度计算熵，硬屏蔽后由既有引擎归一化为资产和现金权重。SAC的密度是得分空间密度，不是归一化投资权重的密度；本阶段没有实现论文温度softmax重加权。
- 双Q、目标网络、自动熵系数和Actor实际优化；重建单独优化，不将其损失随意合并到Actor目标。表示网络同时接受Critic和重建梯度，Actor优化时表示暂时detach。所有数据先按训练日期裁剪，再生成特征与重建样本。
- 当前模型只能称“EarnMore启发的研究适配”。新研究格式为research.json/research.pt，显式local_smoke_only及releaseEligible=false，与生产manifest/model.zip加载路径隔离。权重校验SHA256，加载使用weights_only=True；不是生产发布签名或完整发布审核机制。

## 实际修改

- services/algorithms/src/quant_platform/rl/masked_portfolio.py：共享注意力编码器、掩码解码、等变Actor、聚合双Critic及独立优化步骤。
- services/algorithms/src/quant_platform/rl/masked_train.py：时间隔离、随机掩码、本地训练上限、研究权重保存加载及样本外共享账户回放。
- tools/run_masked_smoke.py：读取已有CR069冻结数据，确定训练/留出股票与ETF，按相同费用回放模型与每日等权再平衡参照；不下载、不写线上。
- apps/frontend/src/dashboard/model-disclosure.js：策略选择前显示“旧单资产模型·仅支持510300”或“多资产组合·2–10只联合决策，共享资金”。未改变策略ID、默认选择、HTTP字段或旧模型能力。
- 对应新增测试，以及spec/PRD/design/task登记与回写。工作分支codex/cr070-maskable-portfolio，基于9037847；原仓库根工作区保留。

## 验证证据

### 合成机制与回归

- Windows已有Torch 2.8.0+cpu，新模块7项测试通过：2/3/10资产等变及填充扰动；掩码目标无泄漏、重建实际学习；SAC Actor/Critic/编码器更新；未来分区修改不影响训练/重建采样；训练、保存加载、样本外回放及权重损坏拒绝。
- WSL既有环境回归674 passed、24 skipped、16 network deselected，33.52秒。无Torch环境将新模块整文件跳过，故跳过较前版增加1；其7项已在Windows实际执行，不把跳过冒充通过。
- 前端117项通过，生产构建632模块成功；本轮没有执行新的浏览器视觉验收，未将构建或文案单测冒充公网验收。
- Ruff及git diff --check通过。首次Windows测试没有pytest，之后复用既有纯Python测试依赖；首次UNC临时目录权限失败，自动审批后用新临时目录重跑成功。一次WSL命令的引号造成network被解释为文件名，未运行测试；改用配置文件内not network标记后完成回归。

在实现工作树复现（python代表已有Windows Torch解释器，测试需可用pytest；未新增安装）：

```text
PYTHONPATH=services/algorithms/src
python -m pytest services/algorithms/tests/test_masked_portfolio.py -o addopts= -q
python tools/run_masked_smoke.py --experiment ../cr069-universe/experiment \
  --output artifacts/新的唯一证据目录 --steps 256

# WSL：工作树相对原仓库.venv
PYTHONPATH=services/algorithms/src:services/backend/src:. \
  ../../.venv/bin/python -m pytest -c services/algorithms/pyproject.toml \
  services/algorithms/tests services/backend/tests tools/test_universe_experiment.py \
  --disable-warnings --maxfail=3

# apps/frontend
npm test
npm run build
```

Windows本次实际测试使用PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，在先加载本机Torch/Pandas后，将已有../../.venv/lib/python3.12/site-packages追加至sys.path复用纯Python pytest；PYTHONUTF8=1。成功临时目录artifacts/cr070-unit-03。Ruff检查三个新增算法文件及tools/run_masked_smoke.py。

### 真实冻结历史小试训

源为已有CR069 experiment，不采集新行情。固定选择24股+8ETF共32训练资产，与10只留出资产（5股+5ETF）互斥。随机2–10资产回合、随机起点；训练截止2026-07-10，验证区间不参与优化，测试回放2026-08-10至2026-09-09。一个seed42，256步、225次优化，训练循环3.61秒。所有重建采样也只使用训练分区。

小试训真实输出如下；等权参照每日再平衡并扣相同费用，不是页面无成本买入持有基准。以下是小样本执行结果，不作算法优劣结论，也没有据测试结果选模型：

| 回放 | 新模型区间收益 | 同成本等权再平衡 |
| --- | ---: | ---: |
| 训练池内10资产、未来时间 | -1.5053% | -1.5340% |
| 留出2资产、未来时间 | -3.8759% | -5.5611% |
| 留出3资产、未来时间 | -5.1781% | -6.6836% |
| 留出10资产、未来时间 | -3.8538% | -4.0421% |

8组回放均验证非负现金、有限净值及资产加现金权重守恒；研究权重保存加载后确定性输出完全一致。执行覆盖不等于所有组合或长期收益泛化。CR069测试日期此前已被研究使用，不是全新盲测。本次未做匹配预算的MLP对照或消融，不能把少量跑赢等权的亏损结果包装成EarnMore收益提升。

证据仅保留于实现工作树ignored artifacts/cr070-real-smoke-01/report.json及model/；模型不入Git。未修改既有模型、行情、数据库、日更、线上页面或服务。

## 下一阶段验收条件

先冻结相同训练资产、日期、费用、步数和多个随机种子的比较方案：现有MLP基线、注意力无重建、注意力加重建，并报告验证选优与锁定后测试。分别评价未见组合、留出资产和未来区间，报告收益、回撤、换手及费用。只有证据支持，才能称为“适应能力提升”；不达标则保留原模型。

回合内换池必须先规定移出资产如何在真实下一开盘清算、停牌持仓如何保留和限制总资产数，不能直接丢弃持仓或重置现金。生产接入还需独立的版本/完整性门禁、披露、API测试及云端回归，本阶段不提前登记完成。


## 第二阶段后续状态（2026-10-20）

同预算研究SAC三路线、三种子及消融对照已完成，详见[第二阶段报告](cr070-comparison-2026-10-20.md)。掩码路线在当前小预算下未优于MLP，不替换线上模型；正式训练、完整收益验证、回合内换池和上线仍未完成。本文第一阶段数据保留，不覆盖为第二阶段结果。
