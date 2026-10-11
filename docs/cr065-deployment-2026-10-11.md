# CR065 需求复核与云端上线记录（2026-10-11）

当前状态：**云服务器后端与前端已上线并通过真实 HTTPS 浏览器验收；GitHub Pages 等待 PR #47 合并及其工作流/真实页面验收。**本记录不将两处发布状态混为一谈。

## 需求逐项核对

| 用户要求 | 已验证状态 |
| --- | --- |
| 默认买入持有、买卖点、持仓比例、交易数、累计费用 | 云端已实现。基准是无费用价格参考；实际佣金/税/滑点分列，旧任务缺失数据明确显示未记录。 |
| 相关性选池带入回测，允许修改，板块联动 | 云端已实现单向继承/手动脱离/恢复，市场日期快捷设置及排行载入；结果保留提交快照。 |
| 回测和模拟使用相同参数、资金和成本 | 云端实际请求逐字段核对通过；模拟以最新发布依据日重放，日期含义明确。旧 AI 不支持模拟时明确阻断。 |
| 排行显示真实测试区间或与回测一致 | 采用显示真实区间。当前批次为 2026-09-09—2026-10-09，前置历史最早 2025-11-03；固定 510300 榜，不声称代表任意组合。 |
| 十资产共享交易环境、联合权重、轮换训练 | **环境/算法研究入口和小规模试训完成；正式组合模型与网页接入未完成。**传统共享回测已上线，并经十资产云候选验证。PPO/SAC/TD3联合环境及随机2–10资产训练代码已推送，研究权重没有发布。 |

因此不能将第三项概括成“正式组合优化模型全部上线”。网页四个旧模型继续只支持510300，不把它们的独立推理标成联合训练；DQN未扩展为连续组合策略。用户尚未确定正式资产名单；本次未重新训练、采集数据或开通收费资源。

## 版本和发布过程

- 功能提交 `d72f8c90a9a0406f725c8c49a600c49b5d96d279`，手机图例修正 `c7a7e810b9999099a273f46f23734e5ab0acbfb9`；分支 `codex/cr065-portfolio-workflow`，已推送，[PR #47](https://github.com/why621/intelligent-quant-analysis-platform/pull/47)。原工作区已有修改保持。
- 本轮发布前离线回归：**596 passed / 23 skipped / 16 network deselected，23.99s**；前端 **105/105**；全算法/后端 Ruff 通过。手机实际截图发现四项图例换行与纵轴标题重叠，登记后增加顶部预留，相关 **31/31** 测试及生产构建通过。
- 源码/前端白名单包93个文件，无模型权重、行情、任务库或凭据。修正版包452691字节，SHA256 `59c8657d199faebc324504969ff6aa77ea7e4fc4c8d7a1539c628860f3301cf7`。
- 云候选基于现有CR062镜像禁网构建，保留其完整运行时。初版打包错误地覆盖`PYTHONPATH`，遗漏`/opt/rlruntime/rl-fix-deps`和`rl-fix-extra-deps`，候选四模型被禁用，六策略排行门禁失败；**该版本从未切换线上**。修正版继承原环境，无重新安装依赖，完整重验通过。没有删除失败检查。
- 正式目录 `/opt/intelligent-quant-cr065-20261011-r2`；镜像 `quant-mvp-backend:cr065-r2`，ID `sha256:d87d350b1634de2f041275ec89559068fb5b4a5a92bdfbb0727b7ed2c152c3c7`。旧CR062镜像和四模型原只读挂载保留。
- 候选使用`--network none`、只读行情/模型、UID999、独立临时任务库：五模块通过；双ETF共享、十股票共享、动量共享及PPO/DQN/SAC/TD3共**7个异步任务全部succeeded**，均243个账户点；六项排行及错资产/错模式/样本内日期拒绝通过。采用真实云业务日期，未固定历史时钟。
- 切换取得日更runner锁，维护入口阻止新回测并排空已有任务。SQLite备份后实际恢复到独立库检查，原**137行**、integrity=ok；切换前后逻辑摘要均 `a2c6d36f351614acee63c2018301dee5b04bc2150a6aba114b503afd3b723dbf`。备份路径为发布目录的`backup/`。
- 后端健康及内部API门禁通过后发布前端；旧哈希资源保留，先资源后原子切换index。准备了故障回滚，本次未触发，不声称已做新的生产故障演练。
- 手机补丁只更新静态前端，不重启后端。最终云入口 **`index-BWJxIfKd.js`**，index SHA256 `7f9d9c5a3f82a494cd1b6facc4d7d761eaad5d623bd65bb339a158087958fb21`；该次入口备份为`backup/frontend-r3-previous-index.html`。

## 实际云端验收与数据保持

真实 [云端网站](https://43.161.223.91/) Edge 验收**33项通过、23个业务请求均成功**，没有pageerror、console error或requestfailed。自动化按已有速率限制间隔发送请求，没有修改限流。验证资产联动、默认基准/共享账户、每日净值守恒、费用核对、ETF零印花税、模拟八项配置一致、排行榜六项和区间、手动覆盖/恢复、排行导入及真实旧任务恢复。

真实新验收任务 `2524e158-440b-46f8-aafc-fe91b91a0afc` 保留在任务库：510300/510500，2025-10-09—2026-10-09，MA8/30，资金120000、现金预留10%、佣金0.04%、滑点0.03%、自动税率，243个账户点/28笔成交。恢复的旧TD3任务仍为 `1248c656-72fa-4bb9-8928-0611eb60a9e1`，未改写旧JSON。原137条保持与新验收任务新增分开记录。

最终手机补丁另做**只读恢复同一新任务**，1440/390/320三视口无横向溢出，SVG实际坐标证明图例与轴标题不重叠；无新增任务和运行时错误。

行情发布指针保持 `e2add7c52b7397163c26362a1035e6af6913ad179b38775d2a7a102b4d36128e`，截止2026-10-09；模型发布文件及四套权重/manifest逐文件哈希不变；两份日更state摘要不变。日更镜像引用随代码升级，timer配置原样、active，禁网dry-run为`waiting_new_day`/targetDate=2026-10-09/continuous，下一次计划2026-10-12 07:30 CST。未采集、补跑、修改业务数据或重置账本。

## GitHub Pages 与未完成事项

本轮已推送源码和文档；只读GitHub确认main受保护，当前环境可用SSH推送，但没有GitHub API创建/合并PR授权。用户已创建PR #47；截至本记录，PR仍open、可合并，功能头c7a7e81的前端/算法/后端及Regression stack四项检查均success。已请求用户按仓库流程合并，没有绕过保护或直接发布gh-pages分支。

合并后应核验main实际SHA、Pages工作流成功、实际页面新入口及跨域请求，再将Pages项标完成。当前云站已升级不代表Pages已升级。正式联合模型训练、最终资产池、模型网页集成和收益/泛化研究仍需后续明确安排。

## 证据与复现入口

原仓库ignored `artifacts/cr065-deploy/`：`cloud-baseline.json`、`archive*.json`、打包/prepare/candidate/cutover脚本、`cloud-candidate.json`、`cloud-browser.json`、真实请求结果、最终`cloud-final-visual.json`及截图。云发布目录含`validation.json`、`deployment.json`、`frontend-deployment.json`和备份；均不将权重、真实缓存或数据库加入Git。

关键命令：

```text
本地：PYTHONPATH=services/algorithms/src:services/backend/src <原仓库>/.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -m 'not network' --disable-warnings --maxfail=3
前端：node --test artifacts/cr065-worktree/apps/frontend/tests/*.test.js
静态检查：<原仓库>/.venv/bin/python -m ruff check services/algorithms services/backend
构建（工作树）：VITE_API_BASE_URL=https://43.161.223.91/api node ../../node_modules/vite/bin/vite.js build apps/frontend --base=/ --outDir ../../../cr065-deploy/cloud-dist-r3
公网验收：node artifacts/cr065-deploy/online_browser.cjs
最终只读视觉：node artifacts/cr065-deploy/visual_browser.cjs
```

数次工具自动审批发生网络传输中断，动作未执行，同一动作重试后获准完成；不是安全判定拒绝，未绕过审批。Windows/WSL和云端证据按层次区分，历史网页反馈未被当作当前故障结论。
