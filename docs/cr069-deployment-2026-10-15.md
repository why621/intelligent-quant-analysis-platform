# CR069 全资产组合模型与动态排行榜云端发布

2026-10-15：用户已授权推送部署。功能与停牌补丁提交 `29ac85ac79fb53fc6196a15ae938ca1a7c36a9d4` 已推送 `codex/cr069-universe-ranking`；云端后端与静态前端已完成备份切换和服务探测。真实公网浏览器及静态资源哈希验收已通过；GitHub Pages 已随 PR #51 合并发布并通过独立真实页面验收，两个入口均已上线。此前“仅本地完成、未授权发布”的记录属于本轮授权前状态。

功能、训练选择与研究限制见 [CR069 本地训练及验收报告](cr069-universe-ranking-2026-10-15.md)。本报告区分离线回归、云端隔离验收、生产容器探测、公网浏览器及 Pages 验收，不能互相替代。

## 发布身份与范围

| 项目 | 实际值 |
| --- | --- |
| 源码提交 | `29ac85ac79fb53fc6196a15ae938ca1a7c36a9d4` |
| 发布包 | `release-r2.tar.gz`，111 个文件、2,258,614 字节 |
| 发布包 SHA256 | `d7c718833377e58ef50e9cda60e566dd719aba3636ac25f5e80254a9a5fb12a9` |
| 发布清单 SHA256 | `7ecfb629de6d61843729b1742978af301ddec8bef27aa0ea2961cdf10c2326a6` |
| 云端目录 | `/opt/intelligent-quant-cr069-20261015-r2` |
| 新服务镜像 | `quant-mvp-backend:cr069-r2` |
| 新镜像摘要 | `sha256:be5f196f07555df8e7b78c84e5109ffe66080d18c4104d861e1018468292fae1` |
| 原服务、保留的日更镜像 | `sha256:2367d3bf7a6d34362f46c81fdbf2a33a31bc553a85da230a043883658b495f62`（CR066） |
| 云前端入口 | `/assets/index-CF2H6Oqx.js`、`/assets/index-Hxego8wd.css` |
| 云前端 index SHA256 | `0419bc0e898999dde916560a78ce118fe4c2aded178c45fd0938f30396e28206` |

发布包包括前后端源码、静态资源、三个新组合模型及其 manifest、evaluation、cross-asset-evaluation 和显式 release 清单。范围证据与模型哈希绑定；不上传训练行情、生产数据库、密钥或个人材料，模型权重不进入 Git。镜像基于已核实的 CR066 镜像禁网构建，不安装新依赖。

三个新模型允许从当前 327 资产目录选择 2–10 只股票或 ETF，按联合权重共享资金、交易成本及现金配置；仍受真实预热、样本外日期和数据完整性约束。旧四单资产模型及其模型目录保持，旧模型限制没有放宽。动态 POST 排行跟随完整研究配置，当前策略采用用户参数，其余采用明确默认参数；旧 GET 代表资产榜继续兼容。模型保持 experimental，不宣称长期超额收益已经证明。

## 首轮云隔离失败与 r2 修复

第一版候选完成前 20 个隔离任务后，第 21 项“区间首日已确认停牌基准”失败。真实资产 `601059` 在 2026-10-13 至 10-14 整个请求区间均停牌，基准先读取区间行情触发 `no tradable history`，返回 503。此时正式服务尚未切换，不能将候选失败描述成线上故障，也没有删除该验收项或更换区间绕过。

补丁限定买入持有基准的读取顺序：先核验请求首日停牌证据，再有界读取此前真实收盘用于估值；整个确认停牌区间禁止成交，不构造 OHLCV、不填补未知缺口、不接受上市前价格或不足预热。新增完整停牌、未知缺日和上市前边界回归，模型权重未重训。44 项定向检查及整合 **674 passed / 23 skipped / 16 network deselected** 通过；跳过项不算通过。随后重新打包、禁网构建 r2 并完整重跑原云隔离检查，保留 r1 失败日志。

## 云端隔离验收

`candidate_cloud.py` 使用固定镜像摘要启动禁网、只读根文件系统容器，限制 1 GiB 内存、1.5 CPU，临时 `/tmp` 和独立输出目录；当前真实发布行情、旧模型及日更校验脚本只读挂载。回测任务使用临时数据库，未连接或修改生产任务库。采用实际云端业务时钟，未将本地历史时钟替代云端验收。

使用数据发布 `589c7eadaec10b680607c3e7b177428137106c80791c1671a80677d8c0dc5dd9`，截止日 2026-10-14，目录版本 `33f99e5228a81019cdfad1c72ad2b896bce6cdb2d5416b5505723d73be95503b`。

- 9 项策略目录、327 资产适用范围核对通过；2 个传统、4 个旧单资产、3 个新组合模型均保留正确身份。
- **21 个隔离回测任务全部成功**：两传统、四旧 AI、三新组合各 2/10 资产及反序输入、五个排行榜对应回测、一个首日且整段确认停牌基准任务。停牌任务保持两个交易日账户记录、零成交。
- **6 组模拟成功**：三组合模型分别 2/10 资产；费用、25% 现金配置回显及资产加现金权重和通过。
- **25 项拒绝或边界检查通过**，其中 23 项为 HTTP 拒绝，另外两项是隔离算法的真实价格截短预热门禁和发布证据不匹配门禁；不把后两项计为公网请求。覆盖重复/超十/目录外资产、旧模型跨资产及共享账户拒绝、样本内日期、错误 modelRef、现金/复权边界等。
- 新排行返回 3 个组合 AI 加 2 个传统策略，实际评价窗口 2026-08-10 至 10-14，共 42 个交易日；逐行与相同配置回测的指标、成本和基准相等。四个旧单资产模型在共享组合配置下明确列为不适用，不回退 510300。旧 GET 排行仍为六项。
- CR067 依赖隔离门禁通过：子进程故意继承无效模型路径，并阻止导入 torch、stable_baselines3、gymnasium；日更校验应用仍仅装配两个传统策略，完整发布五模块检查成功。该检查不等同于执行下一次自动采集。

验收包装层将结果绑定新镜像摘要、源码 revision 和发布清单 SHA256，切换脚本再次比对，避免沿用 r1 结果。主要证据为 `cloud-validation.json`；云端完整临时任务结果保留在 r2 的 `candidate/backtests.json`。

## 生产切换、数据保持及回滚

切换持有 `daily-cr028/runner.lock`，先备份 compose、宿主源码和当前 CR068 前端，启用维护标记阻止新回测提交，排空存量任务。SQLite 在线一致性备份后实际恢复到独立数据库并检查 integrity，再修改服务镜像并重建 backend；实际容器镜像、旧模型/行情/任务库挂载及模型环境配置均核对。前端先复制哈希资源，再原子替换入口，旧资源保留。

生产容器内真实 HTTP 探测确认目录、旧 GET 排行和数据版本正确；以候选原始研究请求执行新 POST 排行，**五项完整结果与候选精确一致，耗时 1.385442679 秒**。这是该次生产容器内请求的实测值，不代表公网浏览器时延、并发压测或服务时限保证。

切换前后任务均为 **142 条**，备份及实际恢复 `integrity=ok`，逻辑 SHA256 均为：

`883f4340aabfcef5fb505f1c3109ed9faeb9ae5e785cb8e39bb2df4edbaa75e3`

此数量和摘要是切换阶段快照。后续公网浏览器新增两个成功验收任务，最终审计逐条核对原 142 条记录不变、仅新增这两个任务；具体编号见下文。

以下保持不变：当前行情指针及数据版本、旧四模型逐文件哈希、每日运行镜像、旧验收及连续日更账本、`run_cloud_daily.py`、`verify_published_provider.py`、`recover_daily_publication.py` 的哈希，以及 07:30 timer 配置和 active 状态。本次服务升至 CR069，**日更独立保留 CR066 镜像及 CR067 隔离补丁**，没有顺手切换日更镜像或重新采集。

部署后日更 dry-run 为 `waiting_new_day`，目标 2026-10-14。当天 07:30 定时任务在本次发布前已经成功；下一次 10月16日 07:30 自动执行仍须届时观察，不能由本次 dry-run 或隔离门禁推断成功。

备份位置：`/opt/intelligent-quant-cr069-20261015-r2/backup`。脚本捕获包括中断在内的异常，恢复旧 compose/镜像、源码及前端；删除范围限定为发布新增源码白名单，并检查解析后路径仍位于对应目录内。旧镜像、首页哈希、行情指针及日更摘要全部恢复核对通过才解除维护；回滚失败保留维护标记。回滚不覆盖生产任务数据库。本次 `rollbackTriggered=false`，回滚分支已准备但未实际触发；不得将其描述为生产故障回滚演练成功。

## 公网浏览器、静态资源与有界负载验收

真实地址 `https://43.161.223.91/` 的 Edge 浏览器验收 **81 项检查通过、40 个实际 API 响应全部成功（38 个 200、2 个 202）、0 个运行错误**。没有替换响应或模拟线上行情。覆盖旧十股池之外的五股票加五 ETF 联合回测、新排行与同配置回测指标/成本相等、费用/现金/日期/资产变更使结果过期、刷新生成不同配置摘要，以及排行载入后的完整回测和模拟配置联动。1440、390、320 宽度无页面横向溢出，桌面和手机截图保留。CR068 的圆环光标、分类展开、开关持久化及减少动态降级均保持。

此次公网验收有界新增并保留两条真实回测任务，以及一次不提交订单的模拟请求：

| 用途 | 任务编号 | 状态 |
| --- | --- | --- |
| 原训练池外十资产 PPO 联合回测 | `0cfeb365-0685-4408-b9ca-d8e43322f470` | succeeded |
| 排行载入后的均线策略回测 | `47a6557b-8a43-4963-a3c7-eb4b5086d77f` | succeeded |

`final-audit.json` 确认服务 healthy、镜像摘要正确、原 142 条任务逐条不变、仅上述两条新任务成功；日更及旧模型、行情发布保持，timer active。`public-files.json` 记录正式 HTTPS 地址的 **12 个前端文件哈希全部与发布构建一致**，包括上述入口和样式。

另做一次有界并发抽样：两个不同配置的十资产排行均返回五项结果，耗时分别 **3.017 秒、3.102 秒**；同时健康检查耗时 **2.816 秒**，均为 200。采样容器内存 `385.7 MiB / 1 GiB`。这是两个请求的抽样，不是持续压测、容量上限或时延保证；健康检查出现等待，后续有更多并发需求时需据实测量。服务每进程最多两个排行计算、30 秒协作预算和前端 45 秒等待上限保持。

## 命令与证据定位

本轮脚本保存在原仓库 ignored `artifacts/cr069-universe`。以下为已执行流程的复现入口；发布 stage 已存在，准备和切换脚本具有防重复保护，不应再次执行本轮生产切换。

```sh
# 工作树：artifacts/cr065-worktree；WSL既有依赖
PYTHONPATH=services/algorithms/src:services/backend/src:. ../../.venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools/test_universe_experiment.py -m 'not network' --disable-warnings --maxfail=3

# 原仓库根目录；Windows Python及严格既有SSH主机校验
python artifacts/cr069-universe/package_release.py
python artifacts/cr069-universe/remote.py upload artifacts/cr069-universe/release-r2.tar.gz artifacts/cr069-universe/cloud_verify.py
python artifacts/cr069-universe/remote.py run artifacts/cr069-universe/prepare_cloud.py --arg d7c718833377e58ef50e9cda60e566dd719aba3636ac25f5e80254a9a5fb12a9 --output artifacts/cr069-universe/cloud-build-r2.txt
python artifacts/cr069-universe/remote.py run artifacts/cr069-universe/candidate_cloud.py
python artifacts/cr069-universe/remote.py run artifacts/cr069-universe/cutover.py --output artifacts/cr069-universe/cloud-deployment.json

# 真实公网浏览器验收入口；使用有界任务账本，保留真实验收任务
node artifacts/cr069-universe/online-browser.cjs https://43.161.223.91/
```

本地证据：`archive-r2.json`、`cloud-build-r2.txt`、`cloud-validation.json`、`cloud-deployment.json`、`frontend-builds.json`、`cloud-before.json`；公网证据为 `online-cloud-browser.json`、`online-cloud-*-ranking.json`、两份 `online-cloud-*-job.json`、`online-cloud-linked-allocation.json`、`online-cloud-backtest/ranking-1440/390/320.png`、`public-files.json`、`load-probe.json`、`final-audit.json` 和 `online-mutations.json`。云端 r2 保留发布清单、image-id、candidate 完整结果、validation、deployment 和 backup；r1 候选日志另存。训练及跨资产证据见本地训练报告，不以本次云发布重复证明训练收益。

## GitHub Pages 发布及正式验收完成

用户合并[PR #51](https://github.com/why621/intelligent-quant-analysis-platform/pull/51)，main提交fbaf82bb069edf2e6e60732dcf22626a88332f8e包含29ac85a。匹配同一提交的[Pages工作流38687898755](https://github.com/why621/intelligent-quant-analysis-platform/actions/runs/38687898755) completed/success，于2026-10-15 13:39:15（北京时间）完成。Frontend、Backend、Algorithms、Regression stack四项CI和Pages部署均success，记录在ci-final.json。

实际[GitHub Pages](https://why621.github.io/intelligent-quant-analysis-platform/)入口index-CizEqEND.js/index-cd9hp8zk.css；12个HTTPS资源逐项哈希与本地Pages构建一致，index SHA256 d6c438f2067ec4730d4afd24614cb27a6568c0f149a4727f1aa1a12d1309226c。

Edge真实页面79项检查通过，37个跨域API响应全部200，0运行错误。验证全目录组合范围、三组合AI加两传统同配置排行、旧单资产模型不适用说明、参数/资产变更过期刷新、指标及费用一致、排行载入、模拟草稿继承及动态开关。1440/390/320布局和桌面/手机截图通过。

Pages复用既有云验收任务和模拟响应，未新增回测或模拟，online-mutations.json保持两任务/一次模拟；其SHA256为0737159631c30eca3eddae721b2ab55986f6415558fb93f2c24c2361c82f1c41。此次没有重复云切换、训练或数据采集。证据为online-pages-browser.json、online-pages-*截图/请求记录、pages-public-files.json和pages-workflow.json；复现入口为node artifacts/cr069-universe/online-browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/。

云端与Pages均已完成，本轮发布没有剩余功能阻断。研究限制仍按本地报告披露；下一次07:30自动日更须届时观察。最终SDD、README、接口说明及验收文档同步至codex/cr069-pages-evidence文档分支，已上线功能属于PR #51/main；文档分支不改变服务或触发重复发布。
