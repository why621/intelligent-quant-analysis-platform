# CR-054 用官方公告原文复核并升级 2015—2024 休市日历证据（2026-09-26）

基线 `main` = `7320702`，分支 `algorithm/rl-long-window`（CR-052 → CR-053 之后）。
范围仍严格限制在 `services/algorithms/**` 与本仓库 SDD/文档；未修改 `services/backend/**`、
`apps/frontend/**`、`packages/contracts/**`。

本轮由用户提供入口：<https://www.sse.com.cn/disclosure/dealinstruc/closed/list/>
（"这个应该是官方公告原文，里面有六页，应该能查看所有原文"）。CR-053 曾把 2015—2024 的
通知原文记为"未取得"，那条结论**是错的**：错的只是我没找到列表页真实分页地址。

## 1. 结论先说

上交所「休市安排」栏目 6 页共 84 条（2013-09-11 → 2026-09-17）全部可抓取。取回覆盖
2015—2024 的 13 份公告正文，逐日机器比对后：**9 个年份双向零差异，升级为 `official-notice`；
2020 年保持 `cross-validated`**。

2020 现已按〔2020〕6号（用户提供，见 CR-055）升级，`cross-validated` 十年清零。以下按 CR-054 当轮事实保留。

本节第一句记录的"84 条（2013-09-11 → 2026-09-17）"当时没有被推出应得的结论：既然栏目最旧一条
落在 2013-09-11，2014 年的年度通知就在其中，第六页实测确有该通知与〔2014〕2/4/6/10 号四份专项公告。
CR-054/055 风险清单里"2015 年之前无证据"因此是范围结论写成了能力结论，已由
[CR-056 实录](cr056-2014-calendar-evidence-2026-09-26.md) 第 2 节更正并把 2014 年入表；2013 及更早
则实测确认为交易所在线归档不可得。

| 年份 | 依据公告（发布日） | 公告休市工作日 | 证据表 | 差异 |
| --- | --- | --- | --- | --- |
| 2015 | 上证公告〔2014〕15号（2014-12-24）+〔2015〕22号（2015-07-21，抗战胜利 70 周年纪念日） | 17 | 17 | 无 |
| 2016 | 上证公告〔2015〕36号（2015-12-24） | 17 | 17 | 无 |
| 2017 | 上证公告〔2016〕25号（2016-12-22） | 16 | 16 | 无 |
| 2018 | 上证公告〔2017〕26号（2017-12-22）+〔2018〕39号（2018-12-20，供 12-31） | 18 | 18 | 无 |
| 2019 | 上证公告〔2018〕39号（2018-12-20）+〔2019〕20号（2019-04-18，调整劳动节） | 17 | 17 | 无 |
| 2020 | 上证公告〔2019〕65号（2019-12-20）+〔2020〕3号（2020-01-16，春节） | 18 | 19 | **表多 2020-01-31** |
| 2021 | 上证公告〔2020〕48号（2020-12-24） | 18 | 18 | 无 |
| 2022 | 上证公告〔2021〕37号（2021-12-20）+〔2022〕51号（2022-12-27，供 12-30） | 18 | 18 | 无 |
| 2023 | 上证公告〔2022〕51号（2022-12-27）+〔2023〕47号（2023-12-26） | 18 | 18 | 无 |
| 2024 | 上证公告〔2023〕47号（2023-12-26） | 20 | 20 | 无 |

公告 URL 全部写进证据表每条记录的 `verifiedAgainst`，`source` 换成该年**年度通知**原文地址。

## 2. 抓取与解析：上一轮为什么失败

- 列表页真实分页是 `s_list.shtml`、`s_list_2.shtml` … `s_list_6.shtml`（从列表页源码里的
  `url=` 属性读出）。我上一轮按 `index_2.shtml` / `list_2.shtml` / `2.shtml` 猜测全部 404，
  于是写下"JS 分页仅返回 2026 条目"的结论——那是我没读源码的产物，不是站点的限制。
  `query.sse.com.cn` 的搜索端点返回错误页，同样不猜 URL。
- 早期条目挂在 `/disclosure/dealinstruc/closed/list/c/…`，2016 年末起挂在
  `/disclosure/announcement/general/c/…`；同一公告在 `dealinstruc/closed/c/…` 下另有镜像
  （`calendar.py` 文档串里那两条 2025/2026 地址即属此类，本轮实测均可达，见第 5 节）。
- 正文服务端渲染在 `<div class="allZoom">`，标题在 `<span id="searchTitle">`。解析器自身
  踩过四个坑，全部改到实测零差异（这些是为了不把公告读错，而不是为了把结果凑上）：
  1. `</p>` / `<br>` 必须先转换行，否则整篇一行，`line.split("另外")[0]` 会截掉后文；
  2. 只按 `休市` 行取日期，"另外，X月X日（星期Y）为周末休市"不参与比对（那是本就闭市的周末）；
  3. 跨年区间带年份前缀（"2018年12月30日（星期日）至2019年1月1日（星期二）休市"），
     正则漏了可选年前缀就会把 2018-12-31 误判成"表有公告无"；
  4. 补休日期用**公告自己标注的星期**钉年份（在候选年 ±1 中取星期相符者），而不是猜。
- 比对必须落到**工作日集合**：区间级比对无意义（公告把周末一并写进休市期间，交易日表只标工作日）。

这四条修正最终落成仓库内的复算工具（第 7 节），而不是留在一次性脚本里：取证的可信度来自
"任何人换台机器重跑还是同一个结论"，不来自一段描述。

## 3. 2020 年为什么不能升级

> **本节结论已被 CR-055 推翻**：原文存在，只是不在「休市安排」栏目，而在「本所公告 · 一般公告」
> 栏目——上证公告〔2020〕6号《关于调整2020年春节休市相关安排的公告》（2020-01-27）把春节休市
> 延长到 2月2日，即 2020-01-31 闭市有交易所原文。2020 现已升级为 `official-notice`，
> 十年 `cross-validated` 清零。链接由用户提供，见
> [CR-055 实录](cr055-2020-spring-festival-notice-2026-09-26.md)。以下按 CR-054 当轮事实保留。

年度公告〔2019〕65号与其后的春节专项公告〔2020〕3号（2020-01-16）文字一致：

> 春节：1月24日（星期五）至1月30日（星期四）休市，1月31日（星期五）起照常开市。

而行情侧证据显示 2020-01-31 当日无K线、2020-02-03 才是春节后首个交易日。差异对应
2020 年 1 月底国务院延长春节假期的临时安排，交易所为此另有临时公告；该临时公告**不在
「休市安排」栏目 84 条里**，本轮按栏目 URL、站点搜索、限定站名的三轮检索均未拿到交易所原文
（只有媒体报道）。按红线"不能为通过验收伪造数据"，2020 年不得标 `official-notice`：
证据表保留 `cross-validated`，并把这条差异、两份已取得的公告原文与推断依据一起写进
`verifiedAgainst`/`note`。若日后取得该临时公告，只需把 2020 的 `basis` 改为
`official-notice` 并补 URL——差异本身已由行情侧证据说明清楚。

## 4. 实际改了什么：只有口径，没有日期

`services/algorithms/data/calendar_closures.json` 的 `closures` 区间**一条都没动**
（脚本只重写 `basis`/`source`/`derivedFrom`/`checkedOn`/`verifiedAgainst`/`note`）。实测：

```text
证据表 closures 与 HEAD 版本逐年一致：True
2015-01-01→2024-12-31 期望交易日：升级前 2431 根 / 升级后 2431 根，序列完全相同
```

2431 与 CR-053 回填 510300 实际得到的根数相同，故本轮**不需要**重新回填、不需要重训，
已产出的四份研究权重与 manifest 记录继续有效。变的只有两件事：这十年的口径从"研究证据"
变成"公告原文证据"，以及闸门随之放行（第 6 节）。

`calendar.py` 的校验器同步收紧一处：审计字段原先只对 `cross-validated` 强制，现在
**只要出现就必须完整**（`derivedFrom` + ISO `checkedOn` + 非空 `verifiedAgainst` 三者齐备）。
只写一半的核对痕迹与一张没有出处的日期清单是同一类洞。不写审计字段的 `official-notice`
条目仍然合法（人工读过公告即可）。

## 5. 顺带复核了内置 2025/2026

`calendar._CLOSURES` 是 CR-052 之前人工核对写入的，本轮用机器比对复查，四份公告原文都与内置表一致：

| 公告 | 结论 |
| --- | --- |
| 2025 年年度通知（〔2024〕38号，2024-12-23） | 18 个休市工作日，与内置 2025 双向零差异 |
| 2026 年年度通知（2025-12-22，`announcement/general` 与 `dealinstruc/closed` 两个地址） | 19 个，与内置 2026 双向零差异 |
| `calendar.py` 文档串所引 2025/2026 地址 | HTTP 200，正文可解析，引用仍然成立 |

## 6. 闸门后果（这是本轮唯一的行为变化）

`AkShareMarketDataProvider` 与 `history_probe.probe()` 都以 `closure_basis(year)` 为准，
因此升级直接改变可请求区间：

| 路径 | 2015—2019 / 2021—2024 | 2020 |
| --- | --- | --- |
| 线上无 cutoff 取数（`allow_research_calendar=False`） | 放行（公告口径已核对） | 仍拒绝："未经官方公告核对，仅限研究回填取数" |
| 探测 worker `probe()` | 放行 | 仍拒绝："probe stays inside officially verified calendar years" |
| 深历史回填 / `--history-root` | 放行 | 放行（研究目录自建 provider） |

（CR-055 之后 2020 亦为公告口径，上表右列的"仍拒绝"已不成立；十年全部放行，见 CR-055 第 3 节。）

线上放行只是"允许请求"，不等于线上真有这十年缓存：`_LOOKBACK_DAYS` 与缓存起点仍是既有约束，
是否把深历史并入已发布快照由后端与发布闸门决定，本轮未触碰。信任锚的边界照旧
（CR-053 §3.1）：`basis` 是声明式的，写表的人若谎报 `official-notice`，代码不会反驳——
本轮的改进是让这份声明**可复核**（每年挂着公告文号、发布日与原文 URL）。

## 7. 验证命令与结果

公告比对**没有停在一次性取证**：解析器连同证据表一起进了仓库，
`services/algorithms/tests/golden/recheck_official_closures.py`（非 pytest 模块，需外网）
会重新抓取证据表里引用的每一份公告原文、按公告自己标注的星期重新定年、展开成工作日集合，
再与本表双向比对；任何"公告有、表里没有"的日期都判失败，"表里有、公告没有"只允许出现在
记录自己写明该差异的 `cross-validated` 年份。

```text
$ PYTHONUTF8=1 .venv/Scripts/python.exe services/algorithms/tests/golden/recheck_official_closures.py
2015 official-notice: 公告 17 个休市工作日, 表内 17, 公告有表无 无, 表有公告无 无
2016 official-notice: 公告 17 个休市工作日, 表内 17, 公告有表无 无, 表有公告无 无
2017 official-notice: 公告 16 个休市工作日, 表内 16, 公告有表无 无, 表有公告无 无
2018 official-notice: 公告 18 个休市工作日, 表内 18, 公告有表无 无, 表有公告无 无
2019 official-notice: 公告 17 个休市工作日, 表内 17, 公告有表无 无, 表有公告无 无
2020 cross-validated: 公告 18 个休市工作日, 表内 19, 公告有表无 无, 表有公告无 ['2020-01-31']
2021 official-notice: 公告 18 个休市工作日, 表内 18, 公告有表无 无, 表有公告无 无
2022 official-notice: 公告 18 个休市工作日, 表内 18, 公告有表无 无, 表有公告无 无
2023 official-notice: 公告 18 个休市工作日, 表内 18, 公告有表无 无, 表有公告无 无
2024 official-notice: 公告 20 个休市工作日, 表内 20, 公告有表无 无, 表有公告无 无
复算通过：12 份公告原文，10 个年份                 # exit 0
```

12 份是证据表**带 URL 引用**的公告数（跨年共用同一通知时只抓一次）；第 3 节的春节专项公告
〔2020〕3号本轮读过正文，但它不在「休市安排」栏目的引用序列里，故不计入。
（CR-055 补进〔2020〕6号后，这条复算变成 13 份、十年零差异。）

```text
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m ruff check services/algorithms
All checks passed!

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms -o addopts="-q -m \"not network\""
335 passed, 14 deselected in 54.69s        # CR-053 时点为 333/13：本轮 +2 离线用例、+1 network 用例

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms/tests/test_deep_history_probe.py -m network -o addopts="" -q
6 passed in 57.20s                          # 第 6 例即新增的"引用公告 URL 仍服务同一文档"

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/backend -o addopts="-q"
146 passed, 3 errors                       # 同 CR-053 §6 的日期依赖既有缺陷，本轮未改后端
```

本轮改动的用例：

- `test_deep_history.py::test_shipped_evidence_table_records_a_per_year_basis`
  —— 原"整表只允许 cross-validated"改为断言逐年 basis 映射（2020 例外）与官方 URL 前缀；
- `test_deep_history.py::test_a_partly_cited_official_year_is_refused`
  —— 新增，钉住第 4 节的校验器收紧；
- `test_deep_history.py::test_published_path_never_leans_on_a_cross_validated_calendar`
  —— 触发年份 2015 → 2020（拒绝后仍断言 `_load_history_cache` 为空）；
- `test_deep_history.py::test_published_path_accepts_an_officially_verified_history_year`
  —— 新增，钉住"闸门按 basis 而非按年份"这一行为，防止日后有人为了省事把整段历史写死白名单；
- `test_history_probe.py::test_probe_stays_in_officially_verified_calendar_years`
  —— 窗口改到 2020（仍 cross-validated）与 2011（无记录），并显式断言 2015 已是官方口径；
- `test_deep_history_probe.py::test_cited_official_notice_urls_still_serve_the_cited_document`
  —— 新增 network 用例，逐个 `official-notice` 年份抓取 `source`，断言正文里能找到记录所写的
  公告标题与文号，防止引用漂移成 404 或换成了另一份公告。

一次性抓取脚本与公告 HTML 留在 `%TEMP%`（研究材料，不入库）；入库的是**复算所需的解析器 +
日期 + URL**，也就是上表的 12 条引用与 `recheck_official_closures.py`。

## 8. 未完成 / 风险

1. **2020-01-31 的交易所临时公告原文仍缺**（第 3 节）。这是十年里唯一一处非公告口径日期。
   —— **本轮之后已由 CR-055 补齐**：〔2020〕6号即该临时公告，2020 年已升级，十年无研究口径残留。
2. 深历史仍只有 510300 一个资产；T-035d 完整版（≥3 seed、多资产、跨资产长期绩效、
   过拟合与幸存者偏差披露）未做。RL 四策略继续 `experimental`。
3. 复算工具与新增的 URL 用例都要外网，默认被 deselect（`-m network` 或第 7 节那条显式命令），
   **不在离线套件里**。所以"证据表 = 公告原文"是可复核的，但不是每次提交都会自动复跑的断言，
   且依赖上交所栏目继续托管这 12 个地址：栏目改版或地址漂移时 `recheck_official_closures.py`
   会失败并要求把相关年份的 `basis` 降级，而不是让过期引用继续被当作公告口径。
   同理，第 7 节那次复算成立只到 `checkedOn` 这个日期为止；日后改动区间列必须先复算。
4. 后端接缝待办不变：`WebRL.model_context()` 的 `outOfSampleStartDate` 与
   `validate_web_request()` 仍按 `trainEndDate` 判样本内，应改用
   `quant_platform.rl.splits.in_sample_end(manifest)`；`test_live_data_acceptance.py`
   fixture 仍只跳周末（CR-053 §6，本轮再次复现：146 passed + 同样 3 errors）。
5. 未推送、未开 PR、未部署；`package-lock.json` 与 `.zcode/` 的改动不属于本轮，未提交。
