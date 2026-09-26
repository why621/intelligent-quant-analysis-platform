# CR-052 单智能体 RL 长窗口训练与深历史回填（2026-09-22）

基线 `main` = `7320702`。范围严格限制在 `services/algorithms/**` 加本仓库 SDD/文档；
未修改 `services/backend/**`、`apps/frontend/**`、`packages/contracts/**`。
需求来源：助教 2026-09-22 反馈条一（训练区间太短、缺验证区间），归算法。

## 1. 结论先说

助教看到的"训练只有 2025-09 到 2026-06"不是训练参数写错，而是**数据窗口本身就只有这么长**，
并且有两道独立的闸门：

| 闸门 | 位置 | 现象 |
| --- | --- | --- |
| 缓存起点 | `data/akshare_provider.py:88` `_LOOKBACK_DAYS = 400`，`update_daily()` 在缓存非空时用 `start = cached["date"].min().date()`（354-356 行） | 日更只会**向后延长**，空缓存只回看 400 天，所以线上 45 个资产最早一根是 2025-07-23（510300 为 2025-08-15，n=267） |
| 休市日历 | `data/calendar.py` 的 `_CLOSURES` 只核对了 2025、2026 | 任何跨 2015–2024 的取数在 `history()` 里先算 `sessions(start, end)`，直接抛 `CalendarUnavailableError: trading calendar not verified for 2015` |

第二道闸门是本项目自己设的完整性红线（"No guessed holiday rules outside these years"），
**不会因为多拉数据而自动打开**：即便腾讯接口能给 2015 年的 K 线，我们也无法判断某个 weekday
到底是休市还是停牌，也就无法证明"缺一根"是数据缺失。因此本轮的交付重点是：把长窗口的
**规则、接缝和证据入口**做实，并把"补哪一年日历"变成一条可审计的显式步骤，而不是靠猜。

实测（未联网）：

```text
$ python -m quant_platform.data.deep_history --root data/research_history \
    --symbol 510300 --start 2015-01-01 --end 2026-06-30 --preflight-only
{"verifiedYears": [2025, 2026], "unverifiedYears": [2015, ..., 2024], "ready": false, ...}  # exit=2
```

## 2. 已实现（本轮）

`data/akshare_provider.py` 与日更链路**未改动**：线上缓存的行为、400 天起点和 publication
规则保持原样，深历史只走下面第 2.5 节的独立目录，避免影响 REQ-02/08/09 已验收的行为。

### 2.1 窗口规则：`rl/splits.py`（新增，纯离线）

- 训练 ≥ 3 年（`MIN_TRAIN_DAYS = 1095`）、验证 1–2 年（365–730 天）、可预留测试区间；
- 训练起点不得早于 `HISTORY_FLOOR = 2015-01-01`；三区间必须按时间严格不重叠；
- 市场形态覆盖按**实测**判定，不手写"这段是牛市"：以 63 根滚动动量给每根 K 线打
  bull / bear / sideways 标签（±15% 带宽），`require_regime_coverage()` 要求每类至少
  20 根，否则拒绝该窗口——这样"覆盖牛熊震荡"可复算、可回归；
- 违规一律 `RLInvalidSplit`（`code = RL_INVALID_SPLIT`），**只在训练 CLI 路径出现**，
  不进入 HTTP 响应，因此本轮未改 OpenAPI/JSON Schema。

### 2.2 训练接缝：`rl/train.py`

- 新增 `--val-start/--val-end/--test-start/--test-end/--history-root/--require-regimes`；
- 区间校验放在 **import torch 之前**：窗口不合规立即失败，不烧训练时间；
- 提供验证区间时，必须真的取到 ≥ `MIN_VALIDATION_BARS = 180` 根留出行情，否则拒绝
  ——"有验证区间"不能只是一个日期字段；`validationBars` 与 `regimeCoverage` 写进 manifest；
- manifest 追加 `valStartDate/valEndDate/testStartDate/testEndDate`（`schemaVersion` 仍为 2，
  理由见 2.4），`bundleHash` 覆盖全部字段，旧字段形状保持不变；
- `--history-root` 读独立研究回填目录，产出权重标记
  `consistency = "research_backfill_unpublished"`、`universeVersion = "research-backfill-root"`。

### 2.3 样本内判定：`rl/policies.py` + `rl/store.py`

- 验证窗口**同样属于样本内**（超参是在它上面挑的）。算法侧统一走
  `splits.in_sample_end(manifest)`，回测起点落在其中一律 `RLInSampleRequest`；
- 只记录了区间字段的 bundle 会被 `validate_split_dates()` 检查自洽（起止成对、不重叠、
  `publicationDate` 不早于样本内终点）；**没有这些字段的旧 bundle 照旧可加载**，
  已上线的 PPO/DQN/SAC/DDPG 权重不被判为损坏。

### 2.4 为什么不动 `schemaVersion`

把它抬到 3 会让 `ModelStore.load()` 拒绝全部已部署权重（现有实现是 `!= 2` 即报错），
那是把"新证据要求"变成"线上故障"。区间字段本身已被 `bundleHash` 绑定，缺失即代表
CR-052 之前的短窗口模型——`test_legacy_bundle_stays_usable_but_is_not_a_long_window_split`
把这条语义钉住：**可用，但不算满足三年要求**。

### 2.5 深历史：`data/calendar.py` 证据表 + `data/deep_history.py`

- 日历仍可在不猜的前提下扩容：`QUANT_CALENDAR_EVIDENCE` 指向
  `{"schemaVersion": 1, "years": {"2015": {"closures": [["01-01","01-02"], ...],
  "source": "https://www.sse.com.cn/..."}}}`；缺 `https` 官方来源、区间倒置、月份非法
  一律拒绝；**不允许覆盖内置 2025/2026**；未提供的年份照旧 `CalendarUnavailableError`；
- `quant-deep-history`（`data/deep_history.py`）：显式 `--symbol` 列表、显式 `--root`、
  `--preflight-only` 先看什么会被挡、`--evidence-out` 落证据 JSON；
  拒绝把结果写进 `QUANT_DATA_DIR`/`data/processed` 线上缓存（新增 `data/research_history/`
  已 gitignore，真实行情不入库）；每个 symbol 一次**整段**拉取，因为 qfq 会在除权后
  重锚整条序列，半段刷新会把两种复权基准混在一起。

## 3. 验证命令与结果

```text
$ .venv/Scripts/python.exe -m ruff check services/algorithms      # All checks passed
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms \
      -o addopts="-q -m \"not network\""
325 passed, 12 deselected in 54.46s
$ PYTHONUTF8=1 PYTHONPATH=services/algorithms/src:services/backend/src \
      .venv/Scripts/python.exe -m pytest services/backend -o addopts="-q"
149 passed in 13.37s        # 与 task.md 记录的后端基线一致
```

新增/改动的用例：`tests/test_rl_splits.py`（窗口与形态规则、旧 bundle 语义、
research-root 出处标记、窗口不合规时不得开始取数）、`tests/test_deep_history.py`
（证据表校验、preflight、拒写线上缓存、整段拉取与 stub provider）、
`tests/test_deep_history_probe.py`（**network 标记，默认 deselect**，见第 4 节）、
`tests/test_rl_train_smoke.py`（合成窗口拉到 3 年以上，并新增"验证区间仍属样本内"端到端用例）。

顺带修掉一处只在 Windows 红的旧缺陷：`tests/test_rl_installed_path.py` 用
`Path("/project/...")` 断言仓库布局，而 Windows 上 `resolve()` 会补盘符；改成真实 `tmp_path`
夹具后 Linux/Windows 同结论。

过程中踩到自己一条：把 `assemble_manifest()` 的 `train_start/train_end` 换成 `split`
时，`services/backend/tests/test_ppo_web.py`、`test_rl_web.py` 立刻 29 个 error——该函数是
跨模块调用点。已恢复旧参数形状、区间走新增的 `windows=`，后端 149 项重新全绿。
**改算法模块的公开函数签名前必须 grep 后端与契约调用方**，这条已进记忆。

## 4. 未完成与下一步（不要当已完成）

> 2026-09-26 更新：本节第 1、2、3 条已由 [CR-053](cr053-deep-history-calendar-evidence-2026-09-26.md)
> 推进到实际执行——network 探针 5 项通过、2015—2024 以 `cross-validated` 证据开放研究回填、
> 510300 已整段回填并在真实 5 年训练 + 2 年验证 + 3 年预留测试分区上完成四算法小规模训练。
> 第 4、5 条（后端接缝、CR-044 文档修订）仍未完成。以下原文保留当轮状态。

1. **没有在本机执行真实深历史回填**（用户明确要求，避免长时间拉数）。
   `tests/test_deep_history_probe.py` 是唯一探测上游能否给出 2015/2018/2020 小窗 K 线的
   用例，默认被 `-m "not network"` 排除。需要授权后单独执行：

   ```text
   PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest services/algorithms/tests/test_deep_history_probe.py -m network -q
   ```

   它只按 `symbol=510300` 拉三个约 3 个月窗口和一段 2012 年区间，**不写缓存**，
   因此不会改变任何已发布数据。探针未跑通前，不声称深历史可得。
2. **2015–2024 官方休市公告尚未采集**，缺它回填一定被挡。建议云端/人工按上交所每年休市
   通知逐年录入证据表（一年一条、带 URL 与核对日期），再执行 preflight→backfill。
3. 回填完成后才有真实三年窗口：至少 3 个 seed、多资产（优先 SSE 代码，`sz000` 成交量
   仍受 SDK 版本红线约束）、幸存者偏差与过拟合披露；本轮**未产出任何真实绩效结论**。
4. 后端待办（不属于本模块，未改）：`WebRL.model_context()` 的
   `outOfSampleStartDate` 与 `validate_web_request()` 的样本内判断仍按 `trainEndDate`
   计算，需改用 `quant_platform.rl.splits.in_sample_end(manifest)`，否则带验证区间的
   模型在 HTTP 入口上会被允许从验证区间起回测（算法侧执行时仍会拒绝）。
   research-root 权重因 `universeVersion` 与已发布快照不同，会被现有
   `universe mismatch` 闸门挡在网页之外——这是预期行为，属研究产物不是发布模型。
5. `docs/cr044-rl-strategies-2026-09-19.md` 的 §5 错误码清单与 §4.2 golden 脚本
   仍需按 CR-045 之后的实现修订，未纳入本轮。
