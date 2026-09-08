# CR-015 云端预览部署交付

2026-09-08（北京时间约20:04切换）；用户当次授权先部署可运行功能。

## 结果

[预览入口](http://43.161.223.91) 已通过公网Edge浏览器验证。前后端均更新，相关性、两种传统策略回测、明确ETF基准、任务恢复、排行及模拟配置可体验。

当前仍50只股票/ETF混合池、已发布截止2026-09-07；概览仍503，完整300只、独立指数、日更/运维、HTTPS及Pages未完成。首页已增加阶段说明，不宣称AI/概览已实现。HTTP仅内部教学演示，不输入敏感信息，不公开推广；许可尚未核验。不是完整MVP验收。

## 版本、备份与数据

- 云目录 `/opt/intelligent-quant-regression`，源码HEAD `af02f826b7dcfd1b8a4fb9fd8bdcf56fe07b8d56`。此前工作保存为0f7ddf0，SSH换行修复af0affa，预览说明af02f826；通过Git bundle快进，无GitHub推送/Pages发布。
- 后端镜像 `sha256:a2bd5590d0f66ef9b23ec2c6a61d5fd056620fd71d4ca4c39122fc4491656ef4`。构建于af0affa，最后提交只改前端/文档，后端复用；标签 `intelligent-quant-regression-backend:release-af02f826`。
- 前端镜像 `sha256:378d4c56f9ffcd6d042f7ee86f161543f8e3263db0027ff33f45064187d80424`，标签 `intelligent-quant-regression-frontend:release-af02f826`，云主包 `index-fytQez_k.js`。
- 两服务healthy；前端0.0.0.0:80、后端127.0.0.1:8000，前端同源/api。最终Pages+云后端方向未改变。
- 完整备份目录 `/opt/intelligent-quant-backups/cr015-preview-20260908-r2`，root-only。含repository.bundle、containers.json、market_data.db和backtests.db；两库通过SQLite backup API备份，integrity_check均ok。
- 回滚标签：两个镜像的 `rollback-cr015`。旧后端ID b4dc5e843dfe（a9c1b95业务），旧前端91b272f03a6f。旧镜像/卷/备份均保留。
- 部署后只读与备份逐值对照：data_status_sync 1条、ohlcv 13275条、cache_metadata 8条完全不变。没有执行日更/旧000迁移，没有启用300候选或删数据；测试新增4个模拟回测任务并保留。

## 验证证据

| 层级 | 实际结果 |
| --- | --- |
| Python离线 | 算法/后端及诊断/迁移/名单/批次测试320 passed、8 network deselected；部署工具另6项通过 |
| 前端 | node --test apps/frontend/tests/*.test.js：52通过；WSL npm run build:frontend成功 |
| 静态/构建 | Ruff、git diff --check、云前后端Docker构建通过 |
| 公网浏览器 | Edge152.0.4191.66，13场景通过、pageErrors为空；真实结果与浏览器fixture分开记录 |
| 云HTTP股票 | history/correlation/ranking/allocation 200，backtests 202后真实worker succeeded；000001规范成交量断言通过 |
| 已知未完成 | overview503；未修改strict-data烟测，也未声称严格MVP通过 |

浏览器使用真实页面按钮：默认510300/510500/159915相关性241样本；均线、动量、显式510500ETF基准回测各242点；刷新恢复无新POST；现金0/100两请求权重合计100。两项输入校验及四项浏览器局部故障/边界注入不是源验证。目录实际50项且API0.4.0分页元数据正确，30d排行返回两策略。回测截图已视觉复核，参数、基准标签、首日=1双曲线及指标正常。

命令（浏览器/HTTP复跑会新增研究任务，无真实订单）：

```text
node tools/verify_m0_browser.cjs http://43.161.223.91 artifacts/cr015-cloud-browser-20260908 --cloud-preview
python3 tools/verify_cloud_research.py --base-url http://127.0.0.1 --end-date 2026-09-07
```

后者在云服务器执行；该日期仅表示本轮发布截止，不代表后续日期仍新鲜。浏览器截图/evidence.json和bundle保留于artifacts忽略目录，不入Git。

测试任务：均线f30ce0fa-c178-4ab5-842f-3858ab759d3b；动量/恢复6baec726-0521-4c87-822b-98ac07a6f62a；ETF比较fcc17a00-2abd-48ed-a7fd-62a21a928b58；股票HTTP9727082d-1a4f-4141-bdc4-d80476300fb7。

## 失败与恢复边界

第一次备份因Windows文本stdin转CRLF破坏远端set/cd，输出错误但末尾exit0；未据此认定成功或切换。原数据/服务未替换，不完整目录及容器临时备份保留、不作为恢复依据。改UTF-8字节输入、增加离线回归后，新r2目录备份成功。工具审批传输失败发生于执行前，复核状态后重试，不属于行情源故障。

Windows直接使用WSL node_modules构建缺Windows原生绑定；使用已有WSL Node构建成功，未删除锁文件或依赖。云缺buildx警告未阻断构建。依赖尚未全部锁定，不据此承诺长期完全可复现。

需要回退时，经当次授权执行：

```text
python tools/deploy_cloud_preview.py rollback --revision af02f826b7dcfd1b8a4fb9fd8bdcf56fe07b8d56
```

该命令恢复两个rollback-cr015镜像并重建容器，保留数据卷；源码仍为新版本，不能随后误build覆盖回滚镜像。不无条件覆盖任务库；数据库恢复须先备份现状和保留新增任务。本批未故意演练切换后的回退，不能称完整恢复演练通过。backup/build有固定基线/新目录门禁，后续发布须新CR核实版本后调整，不能直接重跑。

## 下一步

恢复T-016f停牌/上市/代码变更证据规则，再扩大300行情、独立指数、日频概览和五模块版本一致性，之后日更/恢复/负载及HTTPS/Pages。T-021本批预览交付完成，T-009/T-020和完整MVP未完成；未重新测试东方财富、未抓全300或验证跨日稳定性。
