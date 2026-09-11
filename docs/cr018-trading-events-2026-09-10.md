# CR-018 停牌覆盖与研究规则（2026-09-10）

已实现显式TradingEvent、官方来源/身份/日期/重叠校验、证据集合哈希；coverage可选事件输出complete_with_exceptions、已解释/未知/身份中断和矛盾日期。旧无事件调用与v1候选兼容。provider显式注入事件后允许已解释停牌缺口，未知/矛盾/跨身份序列仍拒绝。回测只在实际开盘成交，净值单独延续最后估值、首日缺价保留现金，不改写OHLCV；相关性披露共同收盘区间、缺任何请求资产不静默缩减。

真实离线证据：`artifacts/cr018-history-replay-20260910`，复用CR-013原观察，HTTP新增0；5只complete、688981为complete_with_exceptions，仍241/242条、2025-09-08停牌，294未采集。新候选六只共1451条（不是1425或补造1452），published=false/priceCoverageComplete=false；原候选未改写。完整Schema、候选/观察哈希和逐日重算已独立通过。官方公告链复用CR-013已核实记录，未声称本轮重新下载PDF或持有原字节哈希。

验证：与CR-017相同隔离全量pytest命令346 passed、8 network deselected，15.57秒；新增10项事件/交易回归，针对组合53通过；前端53通过，WSL构建成功主包index-CYvgx6bg.js。静态检查通过。真实重放命令：

```bash
PYTHONPATH=services/algorithms/src .venv/bin/python tools/prepare_history_batch.py --snapshot artifacts/cr012-universe-20260908 --symbols 600000 600519 688981 000001 002594 300750 --start 2025-09-07 --end 2026-09-07 --events config/trading-events.json --replay artifacts/cr013-history-20260908 --output artifacts/cr018-history-replay-20260910
```

限制：事件不是自动下载器，其他未知缺口仍需具体证据；身份变更只识别并阻止跨代码拼接；整段无成交无法估值仍拒绝。此为T-016f本地规则及已知实样本验收，不是全300覆盖、跨日运维或云验收。下一步T-016h先30只有界验证，再完整300。
