# CR-023 ETF独立覆盖结果

27只旧ETF全部完整，各243条，共6561条；2025-09-09至2026-09-09。实际81次HTTPS，预留上限135次。跨境ETF也保留交易所交易日完整性检查，无删资产或补造行情。

候选：artifacts/cr023-etf27-20260910；candidateId 76fcd758f984617a02b4c50d7584de5434cfa3adda29b8c38dbe9e65df9f7e3b。单只5请求/40秒、总1200秒、串行1秒、三次源失败停止。离线工具2测试通过，完整发布组装时再次逐条验证。未修改线上或默认缓存。

命令：PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m tools.collect_etf_candidate --output artifacts/cr023-etf27-20260910 --start 2025-09-09 --end 2026-09-09。
