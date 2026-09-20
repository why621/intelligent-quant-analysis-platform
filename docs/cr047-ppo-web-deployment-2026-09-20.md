# CR047 PPO网页实验回测上线实录

2026-09-20，用户要求更新到网页并选择先开放已验证PPO。基线main8842e78，新分支codex/ppo-web-20260920。

## 实现与限制

实现提交68f2886，容器路径修复8e27554。PPO继续experimental，新增backtestEnabled显式授权实验回测，其他实验策略不因此开放，排行/配置仍隔离。前端支持服务端string enum模型选择、适用资产/训练日期说明、显式使用样本外区间按钮以及结果模型上下文。后端仅从QUANT_RL_RELEASE指向的部署配置加载白名单模型，校验bundleHash、算法/执行/特征、名单版本；提交和执行均检查资产/复权/样本外日期/至少22根行情。错误转换为不泄露服务器路径的类型化响应。同步OpenAPI、Strategy/BacktestResult契约及调用方。

模型ppo-510300-v2-seed42，仅510300单资产/qfq；训练2025-09-09至2026-06-30、样本外起点2026-07-01、前20根预热。bundleHash为2fb36da2721eb09edd5c68286783a96a2b6bc974bb95071c122a45ae113eee36。权重、部署配置、真实行情和CPU运行依赖只在忽略入库的产物/云端，未入Git。训练快照09-09，线上回测快照09-18；两者数据版本分别保留，名单版本一致。没有重训，没有盈利承诺，没有行情源请求。

## 验证结果

- 默认离线算法/后端396用例通过（含新增9项门禁），2可选模块跳过，8network排除；后续容器路径新增2用例+重跑9门禁共11通过，不与前数重复累计，合计398不同离线用例。修改Python Ruff和git diff --check通过。
- 前端71用例全部通过，Vite生产构建成功。
- 本地真实模型Flask HTTP验证51净值/9成交，收益-0.35530932051394126%，与此前离线结果一致；训练重叠/过短/错误资产/非法modelRef拒绝，配置入口仍拒绝PPO。
- Edge本地与公网实际选择PPO、选择已部署模型、设置样本外区间、提交、轮询到成功、展示模型上下文。1440/390宽度无横向溢出，pageerror为空。截图存在但图片读取工具遇到sandbox helper错误，仅报告DOM/几何自动验证，不声称人工逐像素审阅。
- 首轮云候选在导入RL时发现旧parents[5]路径假设不适用于/app/code布局；未切线上，修复为源码布局repo/models、安装布局cwd/models，显式WebPPO存储路径保持不变。r2候选禁网/只读/1GiB容器运行PPO、双均线、动量反转均成功，真实线上09-18快照各58根；禁止PPO.learn验证没有训练调用。两类RL类型化拒绝通过，运行源码与发布清单逐文件哈希一致。
- 公网HTTPS浏览器PPO任务00e035e8-6951-4b67-bb90-00f972346c54成功，58净值/12成交/收益-0.3237222175560883%。这仅为该窗口实验输出，不是长期效果验收。
- 公网传统回测：双均线96344040-cc05-4dd1-97d6-b74c508a2a96、动量反转29ceeb4b-abbb-425a-91f3-626168b93ac1均成功，各58点；status/coverage/overview/Strategy/BacktestJob契约验证通过，CORS与预检正常。样本内和不足22根返回422，错误模型/资产返回400。
- GitHub新分支当前check-runs为空（尚未创建PR），不能宣称远端CI通过；本地与云端验收分别有上述证据。

## 部署证据

云端网页 https://43.161.223.91/ ，已提供PPO实验回测。部署源码8e27554eaa61a5cb1a88a6ce680c8fba19b0ec12，镜像quant-mvp-backend:cr047摘要sha256:7b94f6595b70dba1d1dae6ddb55350aa8e1fd4735bd2784a2fb7c11515ac31c7。96文件发布包SHA256为82ba3e02f32b4d45173d4aa120ad24f82f1fb09cf8185a8210e4d5d895c24f2d。CPU依赖档案SHA256为0fae4bf565fe070e4b4bd7019e8d90078887e6456b34c29819056d98266dfd36，沿用已验证torch2.14.0+cpu/SB3 2.9.0/Gymnasium1.3.0；与服务器Python3.12/x86_64匹配，实际容器推理验证通过。OMP/MKL各限制1线程，模型只读挂载。

切换持有runner.lock，维护哨兵阻止新回测、排空现有任务、备份数据库并实际恢复校验。54旧任务切换前后逻辑哈希均6e7896e334f46c09d13d670671f06d7398d0b8aa54ca1db1fab1a3949b0931f9；公网验收后57行，原54行逐字段未变。后端/网关healthy，维护已解除。行情指针仍492bf27d9902eda38867e06cb5a494b7f1886c80385c73288779e83097e2718d（09-18），连续/历史账本哈希不变；日更镜像摘要同步、禁网预检waiting_new_day，timer active，下次09-21 07:30 CST。

云端stage /opt/intelligent-quant-cr047-20260920-r2，含validation.json、deployment.json、final-check.json、release-manifest.json；backup含旧compose、旧daily/image-id、前端index、算法/后端源码、SQLite备份与实际恢复库。回滚持锁维护排空后恢复旧compose/image-id/index，compose仅重建backend并重载gateway，验证当前行情后解除维护；代码回滚不能用旧数据库覆盖后续任务。旧CR046镜像保留。失败自动回滚路径已写入cutover脚本，本次没有触发。

本地原工作区artifacts/cr047-ppo-web保存脚本/实际日志/JSON/截图。主要命令：

```text
PYTHONPATH=services/algorithms/src:services/backend/src ../../.venv/bin/python -m pytest services/algorithms/tests services/backend/tests -q -o addopts= -m "not network"
npm run test --workspace @intelligent-quant/frontend
npm run build --workspace @intelligent-quant/frontend
# 真实模型：PYTHONPATH包含两目录rl-fix-deps/rl-fix-extra-deps和fix-pr29算法/后端src，OMP/MKL=1
.venv/bin/python artifacts/cr047-ppo-web/local_integration.py
node artifacts/cr047-ppo-web/browser.cjs
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr047-ppo-web/prepare-r2.sh
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr047-ppo-web/validate-r2.sh
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr047-ppo-web/cutover.sh
node artifacts/cr047-ppo-web/browser.cjs https://43.161.223.91 artifacts/cr047-ppo-web/browser-cloud
.venv/bin/python artifacts/cr047-ppo-web/https.py
.venv/bin/python artifacts/cr047-ppo-web/ppo_https.py
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr047-ppo-web/final_check.sh
```

浏览器Windows NODE_PATH使用已有codex-primary-runtime的Playwright/Edge，严格TLS、不经过损坏本机代理。本地验证服务因0.0.0.0被自动审批拒绝后改为127.0.0.1，本地浏览器验证成功；验证完成后已停止服务。辅助脚本首次Windows默认GBK读文档失败后明确UTF-8，未损坏文件。

## 剩余事项

T030a/b/c/d完成，云端网页可用。GitHub Pages尚未更新：该新分支需创建PR合并main，现有Pages workflow才会发布；当前任务没有GitHub API写入凭据，未创建/合并PR，不伪称Pages已上线。入口 https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/ppo-web-20260920 。之后需核对PR CI、Pages实际发布与页面操作。其他三种RL、长期有效性、下次真实日更验证仍分别待办。
