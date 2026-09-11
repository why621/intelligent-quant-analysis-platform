# CR-019：分阶段完整300只采集

已实现有预算串行采集、进程互斥、预留记账、断点恢复、观察哈希校验、种子复用和连续三次失败熔断。旧6只采样器限额保留，候选不发布。

启动首轮因stdin父进程sys.path未传子进程而失败，旧目录保留25次尝试/125次预留；未获得HTTP证据，不宣称确定零请求。修复worker_environment及无网络导入预检后，用独立r2预算重跑。

- artifacts/cr019-history30-20260910-r2：30只各243条，7290条，90次HTTP，150次预留，66.13秒采集计时。
- artifacts/cr019-history300-20260910：复用30只，新增270只串行完成，实际810次HTTP，1350次预留，592.79秒采集计时；总300只，289 complete、11 gaps、0未采集。
- 名单沿用CR-012官方2026-09-07快照，研究区间2025-09-09至2026-09-09，当前固定名单，有幸存者偏差。
- candidateId：2b30e53ee49118b6938fde501a61353d46aa5295d8996e93ac58a5b9c05b0bcb。

验证：PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools -m "not network" -o addopts= -q --tb=short：363 passed，8 deselected（包含CR-020当时测试）。外部请求是上述单独实采，不与离线测试混算。

11只缺口：600438、600958、601059、601995、688012、688072、688521、001280、002049、002602、300442。CR-022继续证据化重分类；不得把289/300当作完整发布。27只ETF未在此批重新采集。没有改线上数据、推送或部署。
