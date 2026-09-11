# CR-022 全量事件证据与离线重分类

新增显式--offline-reclassify，必须同名单同区间seed，原始观察哈希核验后以新事件版本重算，绝不HTTP；未知缺口/未采集不消失。停复牌/上市证据逐项记录在config/trading-events.json，港交所来源限定明确A股代码的发行人公告。

首轮真实离线重放artifacts/cr022-history300-reclassified-20260910：289完整、9完整含例外、2未知，72746条原始行情；HTTP及预留均0。candidateId f30b5fb9b47d30ce856c850dc8fb240ce825a1d730f5cf8164f4d2b76e02c157。源候选与重放候选完整JSON Schema及哈希通过。上轮最终Python365 passed/8网络deselected；其中重分类及事件20测试通过。

续作补齐一级证据：芯原2025-057（https://static.cninfo.com.cn/finalpage/2025-09-12/1224652741.PDF）确认8月29日至9月11日停牌；拓荆2026-050（https://static.cninfo.com.cn/finalpage/2026-08-11/1225466404.PDF）确认6月29日至7月12日停牌。配置已更新；新的300重算结果待运行回写，不改旧候选。

没有删股票、补造OHLCV、移植停牌日期到其他资产或修改线上。27只ETF仍需独立覆盖验证，完整批次发布与MVP尚未完成。

最终重放已完成：artifacts/cr022-history300-final-20260910，candidateId be831e93d0c4c58d60ae2e0151f8d2908ec794773c4e301cddfeaa6b75eb2ff5；289完整、11完整含官方解释例外、0未知，72746条，0 HTTP，priceCoverageComplete=true。旧候选保留。27ETF后续CR-023完成，完整本地发布及联调由CR-024验收；此前待办文字为阶段历史。
