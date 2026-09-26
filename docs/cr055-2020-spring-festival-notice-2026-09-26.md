# CR-055 补齐 2020 年春节休市调整公告，十年日历全部转为公告口径（2026-09-26）

基线 `main` = `7320702`，分支 `algorithm/rl-long-window`（CR-052 → CR-053 → CR-054 之后）。
范围仍严格限制在 `services/algorithms/**` 与本仓库 SDD/文档；未修改 `services/backend/**`、
`apps/frontend/**`、`packages/contracts/**`。本轮不含新增取数、不含重训、不含绩效结论。

CR-054 把 2015—2024 中九年升级为 `official-notice`，2020 年因 `2020-01-31` 只有行情侧证据而
保持 `cross-validated`。本轮由用户提供该日的交易所原文入口：
<https://www.sse.com.cn/disclosure/announcement/general/c/c_20200127_4991582.shtml>
**这一条是我自己没找到，不是不存在**：CR-054 说过它"不在「休市安排」栏目 84 条里"，那半句仍然
成立——它挂在「本所公告 · 一般公告」栏目（`disclosure/announcement/general`），而我只在
「休市安排」栏目和站内搜索里找过。

## 1. 结论先说

2020 年升级为 `official-notice`。`data/calendar_closures.json` 十年（2015—2024）**全部**为交易所
公告原文口径，`cross-validated` 年份清零；`closures` 区间一条未动。

| 项 | 本轮实测 |
| --- | --- |
| 〔2020〕6号《关于调整2020年春节休市相关安排的公告》（2020-01-27 发布） | 正文第一条："延长2020年春节休市至2月2日（星期日），2月3日（星期一）正常开市" |
| 与年度公告〔2019〕65号合并复算 | 公告 19 个休市工作日 = 本表 19 个，公告有表无 0 处、表有公告无 0 处 |
| 期望交易日 2015-01-01→2024-12-31 | 2431 根，与 CR-053/CR-054 相同 ⇒ 不重填、不重训 |
| 逐份引用公告可复核性 | 16 条"标题+文号+URL"引用全部回抓成功，页面确含所引标题与文号 |

该年记录同时把 2020-01-31 的推断链写进 `verifiedAgainst`，而不是只留一个 URL：6号第二条"原定
于2020年1月31日实施的业务，原则上顺延至2月3日实施"、第四条把原定 1月31日的债券上市日顺延到
2月3日，都与当日闭市一致；它调整的那份公告（上证公告〔2020〕3号，2020-01-16 发布）与年度公告
都写到 1月30日（星期四）休市。

## 2. 复算工具为这条句式的原文加了什么规则

`recheck_official_closures.py` 原来只认两种句式：`X至Y休市`（区间）与 `X休市`（单日）。
6号写的是"延长……春节休市**至2月2日（星期日）**，2月3日……正常开市"：**只有终点，没有起点**，
两种旧句式都取不到任何日期。新增规则（`EXTENDS` + `fill_extensions`）：

- `休市至X（星期Y）` 把 X 记为闭市日，并记为一个"延长终点"；
- 终点的起点不猜：从**同年已引用公告给出的最后一个闭市日**向后补齐到该终点；
- 补齐跨度上限 7 天。起点未写明是一句需要解释的话，所以给它一个会红的边界，而不是放开。

对 2020：已声明的末根是 1月30日，终点是 2月2日 ⇒ 补 1月31日、2月1日、2月2日，工作日只剩
1月31日，正好是本表已有而公告此前缺原文的那一天。规则若解释错，双向比对必红：多补会变成
"公告有表无"，漏补会变成"表有公告无"。这是复算工具本身的行为，不是本轮的手工断言。

## 3. 口径变化带来的闸门后果

`AkShareMarketDataProvider` 与 `history_probe.probe()` 都按 `closure_basis(year)` 判定，不按年份：

| 路径 | 2015—2024 | 2015 年之前 |
| --- | --- | --- |
| 线上无 cutoff 取数（`allow_research_calendar=False`） | 十年全部放行 | 仍拒绝（`trading calendar not verified for 20xx`） |
| 探测 worker `probe()` | 放行 | 仍拒绝："probe stays inside officially verified calendar years" |
| 深历史回填 / `--history-root` | 放行 | 拒绝（preflight `unverifiedYears`） |

**`cross-validated` 这条口径没有失效**，它只是在这张表里没有实例了：证据表机制保留，
用例改为把 2020/2015 在临时副本里降级成 `cross-validated` 来钉住拒绝行为
（`test_published_path_never_leans_on_a_cross_validated_calendar`、
`test_probe_stays_in_officially_verified_calendar_years`）。这样拒绝仍然证明"按 basis 判定"，
而不是"这十年恰好都被放过"。

## 4. 验证命令与结果

```text
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m ruff check services/algorithms
All checks passed!

$ PYTHONUTF8=1 .venv/Scripts/python.exe services/algorithms/tests/golden/recheck_official_closures.py
2015 official-notice: 公告 17 个休市工作日, 表内 17, 公告有表无 无, 表有公告无 无
...（2016—2019、2021—2024 同样零差异）
2020 official-notice: 公告 19 个休市工作日, 表内 19, 公告有表无 无, 表有公告无 无
复算通过：13 份公告原文，10 个年份                 # exit 0

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms -o addopts="-q -m \"not network\""
336 passed, 14 deselected in 54.78s        # CR-054 时点 335/14，+1 来自 accept 用例参数化

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms/tests/test_deep_history_probe.py -m network -o addopts="" -q
6 passed in 60.48s                          # 引用公告逐份复核从 9 份 URL 扩到 16 条引用

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m quant_platform.data.deep_history --root data/research_history \
    --symbol 510300 --start 2015-01-01 --end 2024-12-31 --preflight-only
{"verifiedYears":[2015..2024], "unverifiedYears":[], "crossValidatedYears":[], "ready":true, "reason":""}

$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/backend -o addopts="-q"
146 passed, 3 errors                       # 与 CR-053 §6 的日期依赖既有缺陷一致，本轮未改后端
```

用例改动：

- `test_deep_history.py::test_shipped_evidence_table_records_a_per_year_basis`
  —— 逐年映射改为十年全部 `official-notice`，并断言 2020 记录确实引用〔2020〕6号及其 URL；
- `test_deep_history.py::test_preflight_reports_no_research_only_year_left_in_the_table`
  —— 原 `test_preflight_separates_official_from_cross_validated_years`，改断
  `crossValidatedYears == []` 且 2014 仍为 `None`（CR-056 把 2014 补入后，该断言改为 2014 已核对、2013 为 `None`）；
- `test_deep_history.py::test_published_path_never_leans_on_a_cross_validated_calendar`
  —— 触发口径改为临时副本里把 2020 降级（区间不变），拒绝后仍断言 `_load_history_cache` 为空；
- `test_deep_history.py::test_published_path_accepts_an_officially_verified_history_year`
  —— 参数化为 2015 与 2020 两个窗口，钉住"这十年都是已发布口径"；
- `test_history_probe.py::test_probe_stays_in_officially_verified_calendar_years`
  —— 拒绝窗口换成 2011（无记录）与 2014-12→2015-01（跨年），并新增"把 2015 降级即拒"一段（CR-056 后跨年窗改为 2013-12→2014-01）；
- `test_deep_history_probe.py::test_cited_official_notice_urls_still_serve_the_cited_document`
  —— 从只查每年 `source` 扩到查记录引用的**每一张**公告页（16 条），`>= 13` 下限。

## 5. 未完成 / 风险

1. **7 天补齐跨度是一个解释规则，不是一句原文**。它对 2020 年给出了与行情侧证据、与公告第二/四
   条顺延条款一致的结果，但如果上交所日后出现"延长休市"跨度更长的写法，`fill_extensions` 只会
   拒绝补齐并让该年变红，不会静默放过——届时需要显式改规则并说明依据。
2. 上证公告〔2020〕3号仍只在文字里被引用，没有 URL：它不在「休市安排」栏目，本轮没有逐页翻
   「一般公告」栏目历史列表去找（不猜 URL）。2020 年口径不依赖它（65号 + 6号已足够）。
   —— CR-056 实测补一句，免得下一个人白翻：「一般公告」栏目是分页的**滚动窗口**（约 50 页 ×15 条，
   第 50 页已在 2026-07），翻不到 2020 年；那条 URL 只能靠用户提供或站外检索得到。
3. 2015 年之前（含 510300 上市后的 2012—2014）仍无任何证据年份，preflight 继续拒绝。
   —— **本条已被 CR-056 部分推翻**：栏目第六页就有 2014 年全年通知与〔2014〕2/4/6/10 号四份专项
   公告，2014 年已按同一标准入表为 `official-notice`；2013 及更早则实测确认为交易所在线归档不可得
   （该栏目最旧一条为 2013-09-11，一般公告栏目只留约 750 条），继续拒绝。见
   [CR-056 实录](cr056-2014-calendar-evidence-2026-09-26.md) 第 2 节。
4. 深历史仍只有 510300 一个资产；T-035d 完整版（≥3 seed、多资产、跨资产长期绩效、过拟合与
   幸存者偏差披露）未做。RL 四策略继续 `experimental`，是否转 `available` 由后端依证据决定。
5. 后端接缝待办不变：`WebRL.model_context()` 的 `outOfSampleStartDate` 与 `validate_web_request()`
   仍按 `trainEndDate` 判样本内，应改用 `quant_platform.rl.splits.in_sample_end(manifest)`；
   `test_live_data_acceptance.py` fixture 仍只跳周末（CR-053 §6）。
6. 未推送、未开 PR、未部署；`package-lock.json`（npm 版本差异产生的 `libc` 字段抖动）与
   `.zcode/` 的改动不属于本轮，未提交。
