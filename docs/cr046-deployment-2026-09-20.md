# CR046 修复提交与云端部署实录

日期：2026-09-20。用户本轮明确授权提交修复并部署线上。

## 交付范围

- PR #29 `algorithm/rl-strategies` 已快进从366742a至92abfe6，包含修复608383b与PPO样本外验证记录；主分支未合并，交由用户操作。
- 线上算法源码固定为92abfe6d8063fe28408002b12ac63f5ff19c242a，46个源码文件逐个SHA256验证。
- 现有CR040镜像作为固定基础，禁网增量构建 `quant-mvp-backend:cr046`；镜像 `sha256:782b7d0cc4bcc1ab38cfbd0be7907ed17768bd70217a7b9b0c30a289a2d873d2`。
- 发布包48个文件，SHA256 `da4a6d420967378bc2dfb49e573ca0761b2d2b64f17a249e6da7e39e815c47f1`。仅替换算法源码；后端HTTP实现、前端、行情和模型不变，日更使用同一新镜像摘要。
- RL仍experimental；本次没有部署Torch/SB3或本地模型，没有开放网页RL回测。线上验证覆盖当前已提供的传统策略，不能表述为线上RL验收通过。

## 验证证据

1. 既有CR045离线409个不同用例和Ruff证据见其报告；业务源码此后未变，不重复计数。
2. GitHub提交92abfe6的 `Algorithm tests`、`smoke` 两项均success，PR open/mergeable。
3. 云端候选与CR040均在 `--network none --read-only` 容器加载线上不可变快照；510300/600519 × 双均线/动量反转共4组，逐笔成交、净值、指标完全相同。
4. 切换持有runner.lock、维护哨兵阻止新提交并排空任务，SQLite一致备份实际恢复成功。切换前后52行，逻辑SHA256均为70641fad0013dacc68c9affe6222d73f733c54795085edcb93a2ba2987c012d7。
5. 后端与网关均healthy；加载源码哈希与发布清单一致。外网HTTPS严格证书验证：status/coverage/overview三契约通过，CORS与POST预检通过，首页HTTP200。
6. HTTPS提交两项真实回测，2026-07-01至09-18，均58根净值：双均线f250a057-ea86-4875-80d4-60258f0ea650（2笔成交）；动量反转b0264c2d-016e-47fe-9b95-43576388a2a0（1笔成交）。最终任务54行，原52行逐字段完全未改，数据库完整性ok。第一次测试漏传必填策略参数返回400，按契约补齐参数后成功；未修改线上校验规则。
7. 行情指针保持492bf27d9902eda38867e06cb5a494b7f1886c80385c73288779e83097e2718d，publicationDate=2026-09-18。连续/历史日更账本哈希未变；连续模式禁网预检waiting_new_day，timer active，下次2026-09-21 07:30 CST。本次未调用行情源。

## 命令与证据位置

本地原工作区 `artifacts/cr046-deploy`（忽略入库）：package.py、archive.json、prepare.sh/.log、validate.sh/.log、cutover.sh/.log、https.py/https.json、final_check.sh/.log、ci.py。执行入口：

```text
python artifacts/cr046-deploy/package.py
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr046-deploy/prepare.sh
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr046-deploy/validate.sh
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr046-deploy/cutover.sh
.venv/bin/python artifacts/cr046-deploy/https.py
python artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr046-deploy/final_check.sh
python artifacts/cr046-deploy/ci.py
```

云端部署记录 `/opt/intelligent-quant-cr046-20260920/{release-manifest.json,validation.json,deployment.json,final-check.json}`。备份 `/opt/intelligent-quant-cr046-20260920/backup`，包含compose、日更旧镜像摘要、旧算法源码和jobs备份及实际恢复数据库。归档/脚本不应重复执行：prepare拒绝已有stage，cutover要求CR040前置状态。

## 回滚及剩余事项

旧镜像保留 `quant-mvp-backend:cr040`，摘要89b150401ffae3a961a68a1b6c8e9e28259644d24eda0adb84bb7e38f180275a。若回滚，持有runner.lock并启用维护/排空，恢复备份compose与daily/image-id，以compose仅重建backend，检查健康并重载gateway，再验证当前行情版本与解除维护。代码回滚不恢复旧任务数据库，避免丢失后来生成的任务；SQLite备份仅供灾难恢复按需审阅。切换脚本已含失败自动恢复旧镜像路径，本次无需触发。

T-029a/b/c完成。下一步由用户合并PR29；未来RL网页接入、线上重依赖及模型发布、长期样本外有效性尚未完成，不包含在本次传统服务部署内。上线后首次日更需下次定时触发证据，本次禁网预检不能代替真实自动采集。
