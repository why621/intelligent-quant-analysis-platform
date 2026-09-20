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

## 未上线及下一步

自动审批拒绝了SCP上传到既有ubuntu@43.161.223.91云环境，理由是本轮“实现多资产功能”未被认定为对该目的地源代码/模型/配置上传与部署的明确授权。被拒命令没有执行。之后只在本地制作了不含模型或数据的精简发布包，没有换通道上传、没有部署，也没有改线上数据。

T031a/b/c完成；T031d云候选、切换、公网回归仍未执行。待用户确认将本实现部署到现有43.161.223.91：严格SSH上传精简包、逐文件核验，以当前CR047镜像离线增量构建CR048；候选挂载现有模型/行情只读，验证512100/股票/混合组合及净值加总；持runner.lock维护排空、备份并实际恢复验证任务库后切换backend/daily摘要及前端，验证HTTPS两种PPO请求、原任务逐字段不变和日更禁网预检。失败恢复旧compose/image-id/index和旧CR047镜像，不以旧数据库覆盖新任务。

GitHub Pages亦待本新分支PR合并触发现有workflow；未创建PR，不声称远端CI或Pages已完成。创建入口：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/ppo-multi-asset-20260920 。
