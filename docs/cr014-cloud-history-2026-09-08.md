# CR-014 云服务器腾讯历史只读复测

## 结论

2026-09-08 19:18:24—19:18:33（Asia/Shanghai），在香港服务器43.161.223.91的实际后端容器内取得六只股票的腾讯真实日线。18个HTTPS请求全部200，未发生连接超时或断开；不是读取旧缓存模拟成功。

五只各242条，中芯国际688981为241条，缺2025-09-08这一已核实停牌日。六只共1451条，与本机CR-013相同区间观察逐条完全一致。只证明此次六样本腾讯历史链路可用，不证明东方财富已恢复、全300覆盖或长期稳定。

本轮没有部署、推送、安装依赖、更新行情缓存、创建回测任务或修改线上配置。

## 实际执行位置与版本

- 服务器：43.161.223.91，hostname VM-0-16-ubuntu，SSH用户ubuntu。
- SSH严格校验：沿用同一实例旧IP43.161.219.65已保存主机公钥作为HostKeyAlias；没有关闭StrictHostKeyChecking或接受未知身份。没有读取/展示私钥内容。
- 仓库HEAD：b4634d18abd2409fde9c9cd533dc811dd4ca2f1f（之前发布后的文档提交）。
- 容器：intelligent-quant-regression-backend-1；运行镜像ID `sha256:b4dc5e843dfe6636d08740251dd4c1f479895909f5e367a2c49552340192db15`，与CR-006业务a9c1b95对应，前后检查一致。
- Python3.12.14、AkShare1.18.94、pandas3.0.5；已部署provider类源码SHA256 `a54665b09b745601a2456910adbe851700a26168b93c8eab57a04e46f6b4756d`。
- 本地新history_probe/coverage仅通过stdin在独立Python进程内存加载，现有provider函数负责实际腾讯调用；没有替换容器文件或安装新版本。helper源码哈希保存在环境事件中。

## 样本、预算与结果

固定名单沿用CR-012已验证成员；前复权qfq，请求2025-09-07至2026-09-07。实际市场交易日2025-09-08至2026-09-07，预期242日。

| 股票 | 返回条数 | 基本质量/市场交易日覆盖 | 单只耗时 | HTTP请求 |
| --- | --- | --- | --- | --- |
| 600000 浦发银行 | 242 | complete | 0.655秒 | 3/3为200 |
| 600519 贵州茅台 | 242 | complete | 0.643秒 | 3/3为200 |
| 688981 中芯国际 | 241 | gaps：2025-09-08 | 0.558秒 | 3/3为200 |
| 000001 平安银行 | 242 | complete | 0.687秒 | 3/3为200 |
| 002594 比亚迪 | 242 | complete | 0.569秒 | 3/3为200 |
| 300750 宁德时代 | 242 | complete | 0.527秒 | 3/3为200 |

每只包含web.ifzq.gtimg.cn前置查询1次及proxy.finance.qq.com年度行情2次；总计18，上限30。串行间隔1秒，单只40秒硬截止，SSH驱动300秒上限；禁环境代理、重定向和重试，单响应最多2MiB。此时间是本轮小样本观测，不是性能承诺。

无无效OHLCV、重复日期、非交易日记录或金额空值。自动覆盖仍按全部市场交易日核验，未导入停牌证据，所以688981仍标gaps；该日停牌的官方解释见 [CR-013报告](cr013-history-validation-2026-09-08.md)。没有填价或删掉有效完整性检查，也不能由基本数值检查推定复权经济正确或许可已满足。

## 线上服务状态（与新采集分开）

- 约19:09，云端本机GET /api/health：200，version0.1.0；后端healthy。
- 19:20，GET /api/data/status：200；仍为旧50资产池，latestTradeDate=2026-09-07、updatedAt=2026-09-07T19:43:17.870148+08:00。history=ready，overview=failed，整体stale。
- 同时GET /api/market/overview：503 UPSTREAM_UNAVAILABLE，capability=market-overview。此接口读取概览缓存，**没有触发东方财富新请求**，因此503不能用来认定东方财富当前网络状态。
- 测试没有构造provider存储、调用history缓存写入或update_daily，只用object.__new__创建无存储适配对象并调用_fetch_tencent_inline；Python字节缓存写入被禁用。没有把本次样本冒充50只已日更。

## 工具与证据

- [只读云测试执行器](../tools/check_cloud_history.py)：现有Windows SSH与Python标准库，不需安装依赖；仅向用户指定服务器发送已审阅诊断程序，不发送密钥内容。
- `artifacts/cr014-cloud-history-20260908/cloud-events.jsonl`：云环境、六只观察及HTTP轨迹、质量结果、完成事件。
- `artifacts/cr014-cloud-history-20260908/exit.json`：sshExitCode=0。
- 以上真实行情与输出均在artifacts忽略目录，不入库。镜像/HTTP状态和时刻摘要记录于本文，原始工具响应保留在会话。

实际命令（Windows项目根目录；重复联网必须新输出目录并确认新预算）：

```powershell
& 'C:/Users/wangh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/check_cloud_history.py --output artifacts/cr014-cloud-history-20260908 --prepare-only
& 'C:/Users/wangh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/check_cloud_history.py --output artifacts/cr014-cloud-history-20260908
```

只读离线核对：读取cloud-events.jsonl六个sample事件，分别与CR-013观察文件的records直接相等比较；检查每个httpTrace均200/无error、总数18、尾事件finished。六只1451条全部相等，此复核新增网络请求0。

本地离线命令及结果（WSL）：

```bash
PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest tools/test_check_cloud_history.py services/algorithms/tests/test_history_probe.py services/algorithms/tests/test_coverage.py -o addopts= -q --tb=short
.venv/bin/python -m ruff check tools/check_cloud_history.py tools/test_check_cloud_history.py
git diff --check
```

32项通过（0.54秒），Ruff通过；其中3项为新驱动的纯离线路径/准备保护。不是重新执行全部317项业务测试或前端/浏览器回归；本轮不需要改业务实现/HTTP契约。

## 失败记录及下一步

- 本机审批通信多次失败，未启动命令的失败不算SSH/源请求。首次SSH因新IP没有known_hosts记录被拒绝；查找已保存同一实例旧公钥后严格校验登录成功。
- PowerShell脚本草稿被本机签名策略拒绝，未运行；没有更改安全策略，改用现有Python运行时执行普通诊断工具，未运行草稿已移除。
- 诊断工具首次静态检查有两处格式问题，修正后32项离线及静态检查再次通过；没有重复执行云端采集。
- 当前可以继续基于腾讯历史推进MVP，不需要为本轮腾讯连通性换服务器。保留T-016f优先级：证据化停牌/上市/代码变化处理，再扩大30—50及完整300只。
- 独立指数、日频概览、五模块版本一致性、两日日更及恢复、HTTPS/Pages、授权后的完整云端发布仍未完成。需要判断东方财富是否恢复时，另列其具体接口做限量验证，不由腾讯成功外推。
