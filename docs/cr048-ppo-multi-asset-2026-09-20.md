# CR048 PPO跨资产实验回测交付

2026-09-20。用户要求其他资产也可用。基线main2a73c8e（PR30已合并），实现c5675a780e68af2ddff499b008b0cf54c3d5defd，分支codex/ppo-multi-asset-20260920已推送。

## 行为

- 已部署的同一个PPO模型可用于当前发布资产池内1–10只股票/ETF，包含512100；移除网页/后端请求只能510300的限制。部署配置中的510300保留为现有模型训练来源，不再作为请求白名单。
- 沿用原算法：等分初始资金，各资产独立推理、成交后合并净值；无多资产联合训练，无资产间动态资金调配。本轮没有重训或修改权重。
- 保留模型白名单、bundleHash、算法/执行/特征、名单版本、qfq、样本外起始日2026-07-01，以及每个资产至少22根行情。资产代码/去重/1–10限制仍由HTTP入口校验。任何一个资产短数据就拒绝整个任务，错误消息和details.symbol均指出该资产。
- 前端显示训练资产510300及跨资产效果尚未验证，日期按钮不再替换已选资产；发布截止未加载时禁用按钮，避免写空结束日期。
- ModelContext新增可选assetScope=published_universe、trainingSymbols、portfolioMode=equal_cash_independent、crossAssetValidated=false；历史symbols字段和旧任务仍兼容，缺少新能力字段时客户端仍按旧限制执行。策略保留experimental，排行/配置/其他RL不变。

## 已验证

1. 算法/后端离线401 passed、2 skipped、8 network deselected；本批最后错误消息小修后12项门禁再次通过，不重复计数。74前端测试和生产构建通过，修改Python Ruff、git diff --check通过。
2. 同一本地不可变快照、真实PPO模型、2026-07-01至09-09：512100、600519、512100+600519和10资产请求均成功（各51根净值）。组合每一日净值等于两个独立5万元子账户之和；重复结果完全一致。
3. 10资产实例：510300、512100、600519、510050、510500、510880、510900、511260、512010、512170。运行正确性不等于跨资产收益有效性。
4. 非池内999999、11资产、重复资产、训练重叠均拒绝；单个资产短历史整单拒绝及symbol明确定位经回归验证。6份真实BacktestJob响应通过更新后契约。
5. Edge本地真实网页提交512100成功（任务adfdd636-06f4-4627-9303-2c4542dd6ae8，51点/7成交），混合组合成功（b2a8e963-e43d-40cf-ab01-5692be9db6a6，51点/27成交），选中资产未被日期按钮覆盖；1440/390宽度无溢出、pageerror为空。截图存档，仅声明实际DOM和几何检查，不声称人工逐像素审阅。本地127.0.0.1:5188验证服务已停止。

## 发布包及命令

原工作区artifacts/cr048-ppo-multi包含implement.py、tests.py、local-integration.json、browser-local/evidence.json与截图、frontend-tests.log、contracts.py、package.py、archive.json、release.tar.gz。发布包93文件，仅算法/后端源码、接口契约、前端构建资源、Dockerfile和清单；不包含模型、行情、数据库或CPU依赖。源码c5675a7，包SHA256 d795afebc278527979916b4a97bb311530b7bf3470f9c7be158df7a394f9daaa。复用线上CR047镜像及只读模型，不需重传已有权重。

主要验证命令：

```text
PYTHONPATH=services/algorithms/src:services/backend/src ../../.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -q -o addopts= -m "not network"
npm run test --workspace @intelligent-quant/frontend
npm run build --workspace @intelligent-quant/frontend
# 真实模型脚本使用已有CPU依赖及fix-pr29算法/后端src的PYTHONPATH，OMP/MKL=1
.venv/bin/python artifacts/cr048-ppo-multi/local_integration.py
.venv/bin/python artifacts/cr048-ppo-multi/contracts.py
node artifacts/cr048-ppo-multi/browser.cjs
.venv/bin/python artifacts/cr048-ppo-multi/package.py
```

## 云端部署完成（用户明确确认后）

此前自动审批拒绝上传后未执行云端修改。用户随后明确回答“是”，授权部署到现有43.161.223.91；本次已完成上传、候选验证、维护切换及公网回归，T031d完成。

- 部署源码c5675a780e68af2ddff499b008b0cf54c3d5defd，镜像quant-mvp-backend:cr048，摘要sha256:2d612a1036bd3f9202fab6fa996d50cf35d3c0974e1f9ba92e2e6d15e2bb31d5。离线增量构建，沿用现有只读PPO模型和CPU环境。
- 云候选禁网验证512100、600519、混合组合、10资产，2026-07-01至09-18各58点；组合逐日加总和重复结果一致，非法请求拒绝。
- 持runner.lock维护排空，SQLite备份后实际恢复并验证完整性。备份位置/opt/intelligent-quant-cr048-20260920/backup，原CR047镜像保留。切换前后61条历史任务逐字段不变，逻辑摘要3be9ccb54a5baac082df9f9a3635513783357eba2d011fdce67209288fb2d37a；验收新增4条后总计65条。
- 公网HTTPS Edge真实提交：512100任务496be836-46f5-49d1-9fd5-ed53a3027e10（58点/7成交）；512100+600519任务d8c3e75e-75bf-44a8-8308-287f0de4e859（58点/33成交）。日期按钮保留所选资产，1440/390宽度无DOM溢出或pageerror。
- 传统MA任务ae2fee7b-f78a-478a-a7b5-37a6dae603f7（58点/2成交）及动量任务59ab6816-6637-44d9-8449-44d40458384d（58点/1成交）成功。Strategy、BacktestJob和状态/覆盖/市场概览契约、CORS及预检通过。训练重叠、短历史、错误模型和非qfq均正确拒绝。
- 后端和网关healthy，维护标记移除；09-18行情发布及两份日更账本不变。日更禁网预检waiting_new_day，timer active，下次计划2026-09-21 07:30 CST；未把预检计作下一次真实日更完成。
- 云端入口：https://43.161.223.91/#backtest 。前端index摘要1dd89a57ea2187a8ffa62ed52e16a4a396b98fb451d53219b6bf2d2a554de4a5。

实际命令与证据（根工作区忽略目录artifacts/cr048-ppo-multi）：

```text
python -X utf8 artifacts/cr048-ppo-multi/upload.py
python -X utf8 artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr048-ppo-multi/prepare.sh
python -X utf8 artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr048-ppo-multi/validate.sh
python -X utf8 artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr048-ppo-multi/cutover.sh
node artifacts/cr048-ppo-multi/browser.cjs https://43.161.223.91 artifacts/cr048-ppo-multi/browser-cloud
python -X utf8 artifacts/cr048-ppo-multi/https.py
python -X utf8 artifacts/cr048-ppo-multi/ppo_https.py
python -X utf8 artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr048-ppo-multi/final_check.sh
```

对应*.sh.log、browser-cloud/evidence.json、https.json、ppo-https.json保存实际结果。云端stage /opt/intelligent-quant-cr048-20260920保存validation.json、deployment.json、final-check.json。

## 剩余事项及边界

同一510300训练模型跨资产的运行正确性已验证，跨资产收益有效性仍未验证，继续显示experimental和crossAssetValidated=false。本轮没有重训或开放其他三种RL。

云端网页及GitHub Pages均已更新。[PR #31](https://github.com/why621/intelligent-quant-analysis-platform/pull/31)于2026-09-20 10:20:59 UTC合并，main提交f8c796ad4c441bd7618a863b4186c12723549650；[Pages workflow 35504819136](https://github.com/why621/intelligent-quant-analysis-platform/actions/runs/35504819136)对应提交completed/success。实际页面加载assets/index-CROFwLk9.js，包含published_universe及“使用样本外日期区间”，API指向https://43.161.223.91/api。这里只确认Pages部署工作流，不将其等同全部CI成功。

用户曾反馈截图中日期/结果不符合预期，随即明确表示“可以了”；未复现独立新缺陷，也未实施新的代码修复。记录为用户可用性确认，不推断具体操作或收益表现。T031a/b/c/d及Pages发布核验完成。

本轮仅同步四份SDD、本报告及遗留PR29历史审阅，代码c5675a7和部署记录c311006均已在main中。验证命令：git fetch origin、git log origin/main..codex/ppo-multi-asset-20260920（无遗漏提交）、curl读取GitHub PR/Pages workflow及实际网页JS、文档链接检查、git diff --check。实际查询证据保存在本地artifacts/cr048-ppo-multi/merged-pr.json、pages-run.json、pages-live.html和pages-live.js；这些运行材料不入库。既有测试结果沿用，没有重复计数。本轮文档通过codex/sdd-sync-20260920同步，文档合并与既有上线状态区分。
