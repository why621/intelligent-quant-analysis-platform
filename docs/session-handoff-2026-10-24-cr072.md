# 新会话交接：截至2026-10-24，CR072已推送，Pages待合并核验

> 新会话先读本文，再核对活动工作树的spec.md、PRD.md、design.md、task.md及packages/contracts/openapi.yaml。本文是最新状态快照；较早记录中的“当前”“未发布”等必须按当时日期理解，不可覆盖本文。远端后续状态仍需重新读取确认。

## 1. 最重要的接续信息

- **实际开发工作树**：`/home/wangh/projects/智能量化分析平台/artifacts/cr065-worktree`。
- Windows路径：`\\wsl.localhost\Ubuntu\home\wangh\projects\智能量化分析平台\artifacts\cr065-worktree`。
- 根工作区`/home/wangh/projects/智能量化分析平台`是较旧版本且有用户既有修改，不要在那里覆盖文件、清理或判断当前实现缺失。
- 当前分支：`codex/cr072-requirements-audit`；功能及审计提交 **`f6db8a5`**，已成功推送。
- 上次确认main：`d3ba2d753dc82de7a48d1cc84979ef8a4d7a3faf`，包含已合并PR #57。本次整理没有重新访问远端，不推断main现在是否变化。
- CR072 PR入口：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/cr072-requirements-audit 。已请用户创建并合并，**尚未收到本批次“已合并”确认，尚未完成CR072 Pages发布验收**。
- main受保护；现有Git SSH可推送，没有已配置的GitHub API创建/合并权限。不要绕过分支保护。
- 本交接文件和task.md整理回写目前只在本地，未包含于f6db8a5，也未另行推送。文档整理前WSL Git工作树干净。

## 2. 最近完成了什么

### CR071：增强PPO/TD3已经完成生产接入和上线

在现有掩码注意力SAC基础上，增加独立的掩码注意力PPO、TD3。PPO使用新鲜轨迹、裁剪目标及GAE；TD3使用双Q、延迟策略更新与目标平滑；并非给SAC改名。各自完成65536策略步正式候选训练、327资产40组覆盖与验收，无需重复训练。

复用共享注意力、掩码重建、随机子池及训练回合内换池，借鉴EarnMore可利用部分，并非论文完整复刻。网页一次回测仍使用固定所选组合，不能说已实现网页动态换池。

云端与GitHub Pages均完成CR071发布验收。保留所有旧策略；用户明确撤销了下架普通组合的早期要求。另修复基准归约顺序导致反序输入Alpha/Beta微小差异，以及模拟权重长小数导致320px横向溢出。

### CR072：需求映射与算法取舍审计完成

用户要求对照设计检查业务覆盖，仅在B明显完整替代A时删除A。已形成REQ-01至REQ-11与实际代码、契约、测试的映射。

- **未删除算法**：没有充分证据证明现役算法在业务覆盖与效果上被另一算法完全替代。结构更复杂或短期收益高不等于全面优胜。
- DDPG已不在当前网页或默认研究训练列表，保留历史加载兼容，不存在需要再次删除的线上入口。
- 修复模拟配置提示：“当前所选策略尚不支持模拟配置。请选择列表中支持模拟的传统策略或多资产组合模型。”原文错误暗示所有AI均不能模拟；能力判断逻辑不变。
- 将spec/PRD/design中CR050旧“当前”章节标为历史，避免用独立账户拼接、固定510300排行的早期描述判断今天实现。
- 本批次无接口变化、无模型变化、无重训、无云端数据改写；OpenAPI仍为0.15.0。

详细审计：[CR072需求与算法审计](cr072-requirements-algorithm-audit-2026-10-24.md)。

## 3. 当前十二策略和业务能力

| 类别 | 策略ID | 当前用途与边界 |
| --- | --- | --- |
| 传统 | ma_cross、momentum_reversal | 趋势/反转两种不同规则；可解释基线，支持模拟配置。 |
| 旧单资产 | dqn、ppo、sac、td3 | 仅510300实验回测，较长历史训练；不支持模拟。至少两资产的组合模型不能完整替代它们。 |
| 普通联合组合 | portfolio_ppo、portfolio_sac、portfolio_td3 | 2–10资产，同一PortfolioEpisode、共享资金与成本、联合输出权重；可作为增强模型对照。 |
| 掩码注意力组合 | portfolio_masked_sac、portfolio_masked_ppo、portfolio_masked_td3 | 2–10资产，同一共享账户，增强可变股票池表示；支持回测、排行、模拟，未证明稳定收益优势。 |

**当前六个组合都不是“逐只独立跑再拼净值”**。旧单资产卡片写510300不代表平台只能做510300。

可从平台发布目录300股票+27ETF中选择组合，但须满足区间覆盖、共同交易日、预热与样本外门禁。“全部资产”是该327目录，不是全部A股，存在缺口时应明确拒绝而非填造数据。

核心已实现：默认买入持有基准、买卖点、持仓比例、交易次数及费用；相关性选择默认联动回测，支持手动脱离/恢复；回测、排行及模拟共享研究配置与成本口径。排行随当前组合、日期、资金、成本等重算，正常兼容组合场景为八项，缺数据时不能保证八项。旧固定510300 GET接口仅兼容保留。排行当前策略用所选参数，其他策略使用披露的默认参数。

模拟按最新有效发布日重放形成下一交易日配置，不等于使用历史回测结束日；传统支持1–10资产，联合模型2–10资产。平台仅供研究，不接券商、不提交真实订单。

## 4. 发布和运维状态

- 云站：https://43.161.223.91/
- GitHub Pages：https://why621.github.io/intelligent-quant-analysis-platform/
- GitHub：https://github.com/why621/intelligent-quant-analysis-platform
- CR071生产阶段目录：`/opt/intelligent-quant-cr071-20261020-r1`；镜像标签`quant-mvp-backend:cr071-r1`。详细哈希、备份及回滚记录见发布报告，不凭本文重新部署。
- CR071功能PR #56已合并；Pages工作流39398887382成功。随后证据文档PR #57合并到main d3ba2d7。
- CR071当时确认每日07:30更新任务、旧模型、行情指针和历史任务保留。CR072没有读取timer/journal，不能说本次重新验收了完整日更流程。
- **CR072仅推送并完成Pages生产构建，未核验合并及Pages部署**。构建入口`assets/index-DGsMOs9S.js`，本地文件在`artifacts/cr072-audit-20261024/dist-pages`。此前CR071入口为`index-CeR_RXab.js`。
- CR072发布范围仅审计/SDD文档和前端提示，不需要重部署后端、模型或行情。

## 5. 已有验证证据（区分执行阶段）

| 阶段 | 实测结果 | 证据 |
| --- | --- | --- |
| CR072离线算法/后端/工具 | 688通过，26可选依赖跳过，16网络排除；跳过不算通过 | artifacts/cr072-audit-20261024/regression.xml |
| CR072前端 | 118测试通过，普通构建及Pages生产构建通过 | /tmp/cr072-frontend.txt、/tmp/cr072-build.txt、/tmp/cr072-pages-build.txt |
| CR072本地真实权重与冻结数据 | 12策略、20回测、12模拟、8排行、5配置通过；阻断网络，临时DB | artifacts/cr072-audit-20261024/local-models/report.json |
| CR072公网只读 | health、data/status、strategies、market/overview四GET成功 | artifacts/cr072-audit-20261024/public-readonly.json |
| CR071云端历史验收 | 隔离33回测、12模拟、40负向；云站84浏览器检查通过 | docs/cr071-deployment-2026-10-20.md |
| CR071 Pages历史验收 | 84检查、37成功响应、0页面运行错误；12静态文件哈希一致 | artifacts/cr071-deploy-01/browser/online-pages-browser.json、pages-browser-file-hashes.json |

本地冻结行情截止2026-09-09，模拟时钟固定次日，不能作为当前日线上可用性证据。CR071原152任务保留、总154的结论只对应当时验收，不能不检查便称今天仍154。原始artifacts被忽略，不在GitHub；不得把真实行情、权重、数据库或密钥提交入库。

CR072测试命令（在活动工作树中执行）：

```sh
PYTHONPATH=services/algorithms/src:services/backend/src:. ../../.venv/bin/python -m pytest -c services/algorithms/pyproject.toml services/algorithms/tests services/backend/tests tools/test_universe_experiment.py --disable-warnings --maxfail=3 -o addopts="-m not\ network" --junitxml=artifacts/cr072-audit-20261024/regression.xml -q
npm test --workspace @intelligent-quant/frontend
VITE_API_BASE_URL=https://43.161.223.91/api npm run build --workspace @intelligent-quant/frontend -- --base /intelligent-quant-analysis-platform/
```

真实权重重放入口为`tools/verify_masked_extensions.py`，详见审计报告的参数和Windows依赖说明；不必为了交接重新跑训练或重放。

## 6. 明确未完成和不能声称的内容

1. **REQ-11长窗口目标未全部满足**：六联合模型训练2025-09-09至2026-07-10、验证2026-07-13至2026-08-07，不满足原三年以上训练/一至两年验证目标。此前授权短窗上线不等于长窗完成；也不应因此突然禁用已批准模型。后续另立深历史、多阶段、多种子及未使用窗口评估计划。
2. 长期超额收益和池外稳定泛化没有充分证明。增强PPO/TD3历史参考平均收益分别-3.2024%/-3.1631%；TD3验证股票组-20.926%、混合组+16.249%，不能称稳定优于普通版或推荐为默认最优。
3. 2026-10-24只读快照：发布截至10月23日，326/327历史完整、概况299/300；601059末行情9月14日，10月19–23日未知缺口。根因未确认，不认定停牌，也未修复。
4. 该快照dataVersion为`16a40d4fd6a44e04ca34060a1db5cd7659de93b80fc9600fc64086c0d1262c25`；updatedAt为10月24日07:59:13+08:00。这是当时API值，不是未来状态或日更全部步骤成功证明。
5. 默认基准初始等权买入持有、不再平衡、不计费用、价格口径；不等于含分红全收益或净策略的同成本比较。旧单资产训练奖励税费与网页ETF回评有已披露差异。
6. 固定目录存在历史成分/幸存者偏差；十二策略分组折叠仅建议，未实现。页面加载异常属于历史反馈，未证实当前故障；本机Python下载等待不等于网站故障。

## 7. 新会话建议从这里继续

1. 切到本文活动工作树，使用WSL Git读取状态，保留未提交交接文档及用户修改。再读四份SDD和相关契约。
2. 若用户已合并CR072：只读确认PR、main提交与对应Pages工作流，再检查新静态资源/提示。不能以旧CR071验收替代CR072验收。小提示修改无需重新训练或重新创建大量线上任务。
3. 按实测回写T-CR072-5；没有合并证据前保持“已推送，待合并/验收”。本地交接文档是否同步GitHub按用户后续指令处理。
4. 新功能、长窗训练、数据缺口修复分别先登记范围、任务及验收条件，不自动扩大成本或修改线上数据。用户本轮只要求交接整理。

工程注意：Windows Git访问UNC会误报cli.py、smoke_regression.py修改及sequencer错误；本次WSL Git确认整理前干净。应以WSL Git为准，不为消除误报恢复文件。WSL Python在根`.venv`（相对活动树为`../../.venv`），Windows原生Torch用于既有模型验收；不要误判缺依赖就重装/重训。

关键文档：[CR071训练与实现](cr071-masked-ppo-td3-2026-10-20.md)、[CR071部署](cr071-deployment-2026-10-20.md)、[CR071历史交接](session-handoff-2026-10-20-cr071.md)、[CR072审计](cr072-requirements-algorithm-audit-2026-10-24.md)。

## 8. 可直接粘贴给新会话

> 请先读取`artifacts/cr065-worktree/docs/session-handoff-2026-10-24-cr072.md`，然后在`artifacts/cr065-worktree`工作树核对spec.md、PRD.md、design.md、task.md及相关接口契约。CR071六组合模型已上线；CR072审计与提示修复已推送f6db8a5，合并及Pages验收尚待确认。请保留根工作区既有修改和本地交接文件，不重复训练或部署，不把原始长窗目标、长期收益或未知行情缺口标为完成。先说明已确认状态，再按我的本轮目标继续SDD。

### CR072 合并与Pages静态验收完成（2026-10-24，接续实测）
T-CR072-5完成。GitHub API确认PR #59已合并，main为10b31aeb599ea7374253f8539201ffecad6fba69，父提交包含f6db8a55ddae26fe029a9311f8837b3ecc34515b。对应Pages工作流40064032891、Frontend CI 40064032764、Regression stack CI 40064032817均completed/success。
真实Edge打开Pages并用fetch(cache=reload)/Web Crypto逐文件SHA256核对，12个公网静态文件均与CR072 dist-pages一致；入口assets/index-DGsMOs9S.js。相同哈希的入口包含完整新提示，不含“现有AI模型仅支持实验回测”。本次为提示改动的公网静态验收，没有重跑全业务交互或创建线上回测/模拟，不声称重新验收云端日更、行情或模型收益。
命令：WSL git status --short / branch --show-current / log -1 --oneline / diff --stat / ls-remote origin；PowerShell Invoke-RestMethod读取GitHub commits及actions/runs；在活动树执行node artifacts/cr072-audit-20261024/verify-pages-hashes.cjs。证据为ignored artifacts/cr072-audit-20261024/pages-browser-file-hashes.json，脚本同目录可复现。初次脚本从根工作区启动导致MODULE_NOT_FOUND，改为活动工作树后成功；Windows受限网络调用失败后经执行权限审查完成只读验证，不属于线上故障。
本轮只追加本地文档，保留原交接与task修改，未提交、推送、训练或部署。REQ-11组合长窗、长期超额与池外泛化、601059未知缺口仍未完成；本轮未重查缺口现状。后续这些工作需分别登记范围、验收与预算，不能因发布完成而一并关闭。
