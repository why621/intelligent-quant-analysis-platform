# CR-053 深历史休市证据与真实长窗口训练（2026-09-26）

基线 `main` = `7320702`，分支 `algorithm/rl-long-window`（CR-052 之后）。范围仍严格限制在
`services/algorithms/**` 与本仓库 SDD/文档；未修改 `services/backend/**`、`apps/frontend/**`、
`packages/contracts/**`。本轮由用户当次授权执行 network 探测与**单资产**回填，并明确要求
"训练别搞太大，跑个小的确认过程不报错"，因此不含全量拉取与任何绩效结论。

## 1. 结论先说

CR-052 留下的两道闸门中，第二道（2015—2024 休市日历未核对）本轮**以交叉核对证据打开研究通道**，
官方公告原文仍未取得；深历史与真实长窗口训练链路已在真实行情上跑通，并暴露出一个只有真数据
能发现的 manifest 缺陷。

| 事项 | 结果 | 证据 |
| --- | --- | --- |
| 上交所年度休市通知 2015—2024 原文 | **未取得** | 该栏目为 JS 分页，抓取只返回 2026 年条目；搜索仅命中当年新闻。未猜测 URL |
| `akshare.tool_trade_date_hist_sina()` | 可用，零新增依赖 | akshare 1.18.80，`py_mini_racer` 已在环境中；返回 8797 行交易日（1990-12-19→2026-12-31，无重复、无周末被判为交易日） |
| `cn_stock_holidays` | **不采用** | 非 akshare 函数（`hasattr` 为假）；口径是国务院法定假日，与交易所休市不等价（调休补班的周末交易所仍闭市，临时休市未必收录） |
| 候选日历可信度 | 双向零分歧 | 见第 2 节两项独立观测 |
| 上游深历史可达性（T-035c） | 通过 | network 探针 5 passed，2015/2018/2020 小窗与 2012 上市后窗口均有合规 K 线 |
| 真实长窗口链路（T-035d 缩减版） | 通过 | 四算法完成 5 年训练 + 2 年验证 + 3 年预留测试，样本外推理正常，验证窗口一律拒绝 |

## 2. 休市日历：把"猜假日"换成可复算的交叉核对

新浪那张表是第三方镜像，akshare 源码里就写着它曾缺 `1992-05-04` 需要手工补——这种表不能当权威，
但足够好的地方是：它可以**生成候选**，再拿我们已有的两份独立观测去证伪。

按工作日展开成"休市工作日集合"后比对（区间级比对无意义：公告把周末一并写进休市期间，
交易日表只标工作日）：

1. **与官方公告口径**：内置 `_CLOSURES`（2025/2026，2026-09-07 人工核对自上交所年度通知）
   的 18 / 19 个休市工作日，候选表**逐日一致**；且全表 8797 行里没有任何周末被判为交易日。
2. **与真实成交**：腾讯通道（也就是回填实际使用的那条通道）拉 510300 前复权日线
   2015-01-05→2024-12-31 共 2431 根，逐年双向比对——候选休市日出现真实 K 线 **0 天**，
   候选交易日缺失 K 线 **0 天**，逐年成交根数 242—244（与 A 股历史年数吻合）。

2015-09-03~04（抗战胜利 70 周年阅兵临时休市）与 2020-01-24 + 01-27~31（春节延期）这类
临时安排都自然出现在候选表里，说明它记录的是交易所口径而不是法定假日口径。

两项核对都固化进 `tests/test_deep_history_probe.py` 的 network 用例：任何一侧上游漂移，
证据表立刻不再被接受，而不是继续被引用。

## 3. 边界：cross-validated 年份只服务研究，不进入线上路径

`data/calendar_closures.json`（新增，仅日期与 URL，不含行情）每条年度记录必须声明 `basis`：

- `official-notice`（默认）：人工读过 `source` 处的交易所通知；
- `cross-validated`：通知原文未取得，因此额外强制三项——`derivedFrom`（候选从哪张表来）、
  `checkedOn`（核对日期）、`verifiedAgainst`（哪些独立观测逐日一致）。缺任一项直接拒绝，
  一张没有出处的日期清单不被接受。

内置 2025/2026 永不被证据文件覆盖（`parse_evidence` 原有红线）。

关键的隔离在 `AkShareMarketDataProvider`：默认情况下，**没有 publication cutoff 的线上取数路径**
一旦请求跨到 `cross-validated` 年份就抛
`UpstreamUnavailableError("休市日历 [2015..2024] 未经官方公告核对，仅限研究回填取数")`，
且当场不写缓存（测试断言 `_load_history_cache` 仍为空）。只有两条显式接缝可以打开它：
`quant-deep-history` 回填与 `quant-rl-train --history-root`，二者都把
`allow_research_calendar=True` 设在自己新构造的、指向独立研究目录的 provider 实例上。
已发布快照的研究路径（`read_only_research` + cutoff）行为不变：缓存不含 2015 时依旧报
"published history incomplete"。`schemaVersion` 仍为 1，新字段向后兼容。

### 3.1 自查后的两处补强

**证据表现在无需环境变量即生效**（`DEFAULT_EVIDENCE_PATH` 指向仓库内的
`services/algorithms/data/calendar_closures.json`），意味着一次普通的部署就让 2015—2024 在整个
代码库里"可解析"。逐点核对了所有直接调用 `sessions/is_session/latest_session` 的位置：
排行/配置/引擎/发布/覆盖度/指数快照的窗口都由线上缓存或请求区间导出（当前缓存起点 2025-07-23），
不会因为日历变宽而多取一天数据；唯一能由外部输入任意区间的入口是隔离的探测 worker
`history_probe.probe()`——它在本次补强前会**由"2016 年历未核对"这一响亮拒绝变成静默可行**，
即用一个研究口径的日历去给"某段历史是否可达"下结论。已改为只接受
`closure_basis(year) == "official-notice"` 的年份，跨年窗口（如 2024-12→2025-01）同样拒绝，
既有 2025/2026 用法逐字节不变。用例：`tests/test_history_probe.py::test_probe_stays_in_officially_verified_calendar_years`。

**信任锚的边界要说明白**：`official-notice` 这一 basis 是**声明式**的——部署方若把某年写成
`official-notice`，闸门不会反驳，这与内置 2025/2026 表当初依赖人工核对是同一条信任边界，
不是新洞；`cross-validated` 才是本轮新增的、必须交出 `derivedFrom/checkedOn/verifiedAgainst`
的口径。另需注意探测 worker 由 `tools/prepare_history_batch.py` 以子进程启动，它会同样读到默认证据
文件——因此该 worker 的年份闸门不能依赖调用方是否设置了 `QUANT_CALENDAR_EVIDENCE`。

无环境变量下的实测（新进程）：

```text
$ env -u QUANT_CALENDAR_EVIDENCE python -c "...calendar.closure_basis(2020); provider.history('510300',2016-01-04,2016-03-31)"
evidence path: services/algorithms/data/calendar_closures.json   # 默认证据即生效
basis 2020: cross-validated
verified years: [2015..2026]
refused: 休市日历 [2016] 未经官方公告核对，仅限研究回填取数        # 线上路径仍拒绝
```

## 4. 真实数据验收（本轮实际执行）

```text
# 1) 深历史可达性 + 证据复审（network，默认 deselect）
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms/tests/test_deep_history_probe.py -m network -o addopts="" -q
5 passed in 76.55s

# 2) preflight：证据表就位后放行
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m quant_platform.data.deep_history --root data/research_history \
    --symbol 510300 --start 2015-01-01 --end 2024-12-31 --preflight-only
{"verifiedYears":[2015..2024], "unverifiedYears":[], "crossValidatedYears":[2015..2024], "ready":true}

# 3) 单资产整段回填（写独立目录，不触碰线上缓存）
$ ... --evidence-out data/research_history/backfill_evidence_510300.json
{"symbol":"510300","adjust":"qfq","bars":2431,"firstDate":"2015-01-05","lastDate":"2024-12-31"}
$ ls -l data/processed/          # 线上缓存 mtime 仍为 2026-09-19 19:53，未被改写

# 4) 真实分区训练（小 timesteps，仅为验证链路）
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m quant_platform.rl.train --history-root data/research_history \
    --models-root data/research_history/models --run-id ppo-real-2015-2021 --algo ppo --symbol 510300 \
    --start 2015-01-05 --end 2019-12-31 --val-start 2020-01-02 --val-end 2021-12-31 \
    --test-start 2022-01-04 --test-end 2024-12-31 --require-regimes --seed 42 --timesteps 4096
{"runId":"ppo-real-2015-2021", ...}      # dqn/sac/ddpg 同分区 --timesteps 2048 亦全部完成
```

PPO manifest 实测记录：`trainStartDate=2015-01-05 / trainEndDate=2019-12-31`（5 年）、
`valStartDate=2020-01-02 / valEndDate=2021-12-31 / validationBars=486`、
`testStartDate=2022-01-04 / testEndDate=2024-12-31`、
`regimeCoverage={bear:125, bull:131, sideways:900, warmup:63}`（助教要求的牛/熊/震荡由价格动量实测）、
`publicationDate=2021-12-31`、`consistency=research_backfill_unpublished`、
`universeVersion=research-backfill-root`、`schemaVersion=2`、`executionVersion=account-feedback-v2`。

预留测试区间推理（2022-01-04→2024-12-31，726 根）：

| algo | 信号 | 取值范围 | 落在验证区间 |
| --- | --- | --- | --- |
| ppo | 705/726 非空 | 0.0 — 0.293 | `RLInSampleRequest`（样本内终点 2021-12-31） |
| dqn | 726/726 | −1.0 — 1.0 | 同上 |
| sac | 705/726 | 0.402 — 0.696 | 同上 |
| ddpg | 705/726 | 3.9e−06 — 1.0 | 同上 |

**这批权重的意义仅止于链路正确性。** timesteps 是 4096/2048（收敛训练量级的零头）、单资产、
单 seed，`--require-regimes` 只证明训练窗覆盖三种形态，不证明策略赚钱。RL 四策略继续
`experimental`，是否转 `available` 由后端依证据决定。

离线与静态检查：`ruff check services/algorithms` 通过；算法离线 **333 passed, 13 deselected**（52s，
含第 3.1 节自查补强的新用例）。
后端回归 `pytest services/backend` 为 **146 passed, 3 errors**，3 例即第 6 节那个日期敏感的既有
fixture 缺陷，非本轮引入（CR-052 登记时的 149 passed 对应 2026-09-22/23 的运行，当时起点不是休市日；
本轮未据此改动任何断言，只按第 6 节移交）。

## 5. 真数据暴露的缺陷（离线测试为什么没抓到）

`--history-root` 首次真实运行即被自家 store 拒绝：`invalid publication date`。根因是
`_unpublished_context()` 把 `publicationDate` 记成**训练段末根**（2019-12-31），
而 CR-052 新加的规则要求 `publicationDate` 不早于样本内终点（`valEndDate`=2021-12-31）——
验证区间同样是模型见过的数据，快照日期必须覆盖它。

离线套件当时全绿，因为 `tests/test_rl_train_smoke.py` 的桩 provider 直接提供
`publication_context`，**从不经过 `_unpublished_context` 这条研究分支**。已修：
`train_run` 记录实际观察到的每一段行情（训练 + 留出验证），`_unpublished_context` 取其末根最大值，
并补 `test_publication_date_must_cover_the_validation_slice_not_just_training` 作离线回归。

顺带修正自己的探针缺陷（不是放宽检查）：`test_upstream_reaches_pre_2015_history` 原本探
2012-01-30~03-30，而 510300 **2012-05-28 才上市**，空返回是正确行为。实测上游首根可得分界正是
2012-05-28（388 根，2011→2013 窗口），故把窗口移到上市之后并加一条"不早于上市日"的断言。

## 6. 与本轮无关、移交后端的发现

`services/backend/tests/test_live_data_acceptance.py` 的 `stack` fixture 用
`day = date.today()` 而只跳过周末（`while day.weekday() >= 5`），不跳过休市日。今天 2026-09-26
回退到 2026-09-25 恰是内置日历里的中秋休市日，`latest_session()` 给 09-24，于是 3 个用例在
fixture 阶段 `ValueError: future or obsolete market timestamp`。`git diff main --stat` 证明本轮
未改 `market_fetch.py` 与该测试，属日期敏感的既有缺陷（逢节假日起点当天必红），建议后端把
fixture 改为 `calendar.latest_session(date.today())`。本轮未修改后端文件。

## 7. 未完成（不要当已完成）

1. **2015—2024 官方休市通知原文仍未取得**。当前十年是 `cross-validated` 证据，只可用于研究回填；
   若日后逐年拿到交易所通知，请把 `basis` 改回 `official-notice` 并保留 URL 与核对日期。
2. **深历史只回填了 1 个资产（510300）**。多资产训练仍需按 D-04 与 sz000 成交量红线选择代码，
   并且每多一个资产就多一次整段 qfq 拉取——需要单独授权，不在本机批量执行。
3. **T-035d 的完整版未做**：≥3 seed、多资产、跨资产长期绩效、过拟合与幸存者偏差披露。
   本轮明确按"小规模、只验证不报错"执行。
4. 后端接缝待办不变（未改）：`WebRL.model_context()` 的 `outOfSampleStartDate` 与
   `validate_web_request()` 仍按 `trainEndDate` 判样本内，应改用
   `quant_platform.rl.splits.in_sample_end(manifest)`。
5. research-root 权重因 `universeVersion` 与已发布快照不同，会被现有 universe mismatch 闸门
   挡在网页之外——预期行为，属研究产物。
6. 未推送、未开 PR、未部署；`package-lock.json` 与 `.zcode/` 的改动不属于本轮，未提交。
