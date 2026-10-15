# 前端应用

`apps/frontend` 是智能量化分析平台的 Vue 3 + Vite 前端，使用 ECharts 展示市场、相关性、回测、策略排行和资产配置结果。

## 已实现功能

- 首页启动时并行读取数据状态、资产列表、市场概览和策略目录；排行由用户按当前研究配置提交计算。
- 相关性、回测和资产配置页面通过后端 API 获取真实结果。
- 回测任务支持提交、轮询状态和展示指标/资金曲线。
- 后端暂时不可用时，仅使用固定的资产与页面展示兜底；不会随机生成排行、回测或配置结果。
- API 错误、数据过期和更新中状态会在界面中明确提示。

接口字段以 [OpenAPI 契约](../../packages/contracts/openapi.yaml) 为准。

## CR069 云端与Pages已上线（2026-10-15）

- 新组合模型通过明确的全目录范围和跨资产证据开放当前327资产池中的2–10只股票/ETF；展示训练成本、实际执行费用及预留现金，旧模型保留各自范围限制。
- 排行读取当前回测草稿，通过POST /api/strategies/ranking手动计算；当前策略沿用用户参数，其余策略展示各自默认参数。显示完整评价区间、资产、成本和不可参与原因。
- 编辑配置或切换行情版本后，旧榜标记过期并禁止载入，迟到响应不会覆盖新配置。载入有效排行时恢复完整回测配置，并沿既有机制同步模拟。
- 116项前端测试及632模块生产构建通过；真实本地页面78项检查、31个API响应均成功，1440/390/320布局通过。已推送并部署云站，Pages已随PR #51合并发布并通过79项实际检查。云站81项真实浏览器检查和40个接口响应通过，详见[发布记录](../../docs/cr069-deployment-2026-10-15.md)。

详情见[CR069验收](../../docs/cr069-universe-ranking-2026-10-15.md)。下文带日期的发布段落保留历史批次语义。

## CR065 发布状态（2026-10-11，云站与Pages已上线）

- 回测默认显示所选资产初始等权买入持有基准，并增加真实成交买卖点、每日持仓比例、交易次数、累计费用及滑点成本。基准不再平衡、不计费用；旧任务缺失的解释字段显示“未记录”。传统策略使用共享组合资金账户，参数、现金预留与成本一并提交。
- 市场截止日快捷设置研究日期；相关性资产与日期默认同步回测，回测资产、策略参数、资金、现金和费用默认同步模拟。下游修改可解除对应继承并随时恢复；联动仅更新草稿，不自动创建回测或模拟请求。已返回结果保留提交快照，配置或数据版本变化时提示。
- 排行继续使用固定510300及其实际评价窗口，展示评价起止、前置运行历史、观察点数与费用。评价起点可能已持仓；载入回测会保留预热历史说明，不把完整回测指标冒充同窗排行指标。
- 模拟从共享起点重放至最新发布交易日，生成下一交易日配置，参数/资金/现金/成本与回测默认一致。现有AI模型不支持模拟时明确阻断，需用户显式选择传统策略。

新的联合多资产RL环境仅提供算法研究入口及本地小规模CPU烟测，尚未加入网页策略目录，也未发布新权重。既有单资产模型仍按旧模式、原训练范围和实验性状态披露，不能将其称为新组合模型。

本轮云站和配套后端已部署，功能分支已推送PR #47；PR已合并，Pages入口index-BR1Ms9tA.js，33项实际浏览器检查通过。最终云入口index-BWJxIfKd.js，手机图例换行留白修正已验证；未采集新行情，四个旧模型与07:30日更配置保持。详见[CR065上线记录](../../docs/cr065-deployment-2026-10-11.md)及[本地验收](../../docs/cr065-validation-2026-10-11.md)，云站与Pages分别核验。

## 本地开发

在仓库根目录执行：

```bash
npm install
cp apps/frontend/.env.example apps/frontend/.env.local
npm run dev:frontend
```

默认访问 `http://localhost:5173`。按 .env.example 设置 VITE_API_PROXY_TARGET 后，开发服务器会把 `/api` 代理到 `http://localhost:8000`，因此请同时启动后端。

环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | 浏览器请求的 API 基础路径 |
| `VITE_API_PROXY_TARGET` | 未设置时不启用代理 | Vite 开发代理目标 |

跨域部署时，可把 `VITE_API_BASE_URL` 设置为完整后端地址，并在后端 `ALLOWED_ORIGINS` 中加入前端来源。

## 构建检查

```bash
npm run build:frontend
```

## GitHub Pages 说明

Pages 工作流只发布静态前端，无法运行 Flask、SQLite 或后台任务。若未配置公网 API，Pages 页面只能展示不依赖后端的固定内容和“服务不可用”状态。要展示完整业务数据，需要在构建时提供公网 `VITE_API_BASE_URL`，并单独部署后端。


## CR063/CR064 视觉与布局（2026-10-02）
全页面低亮度青绿/紫灰光影、紧凑表单/结果分组、手机策略网格和有限时长动效。样式集中在src/styles/polish.css；系统prefers-reduced-motion关闭动效，空图表紧凑显示、真实结果更新后resize，ECharts按需注册标题及图例。不修改API、计算或模型披露语义。
前端95项测试、四种宽度本地浏览器与云端桌面/手机验收通过；云端与GitHub Pages均已部署CR064，PR45/2ca1d76合并后实际桌面/手机及跨域接口验收通过。完整结果见[CR064报告](../../docs/cr064-ui-density-2026-10-02.md)。

```bash
npm test --workspace @intelligent-quant/frontend
# 云站根路径
npm run build --workspace @intelligent-quant/frontend -- --base=/
# Pages：按工作流同时提供公开HTTPS VITE_API_BASE_URL
npm run build --workspace @intelligent-quant/frontend -- --base=/intelligent-quant-analysis-platform/
```

## CR066（2026-10-12，云端与Pages已上线）
新增三个联合组合模型，可从明确十股票训练池选择2–10资产。共享回测与模拟、训练/验证/测试区间和冻结评估、逐资产权重图已接入；旧模型保持。599算法后端、106前端、13云候选任务通过，云站/Pages各19项真实页面检查通过，详见[CR066报告](../../docs/cr066-validation-2026-10-12.md)。

### CR068 云端前端发布完成（2026-10-15）
用户授权后已推送codex/cr068-ui-motion，功能ec36718、发布登记0f7848c。仅静态前端包323368字节，包SHA256 c40272e24dc581c04d8492acd84b9281a112fa9bcb46cf42fb4c80cec1bd452b；云目录/opt/intelligent-quant-cr068-20261015，backup/web保留旧入口及资源。先校验清单、备份、复制哈希资源，再原子切换index，保留旧资源并准备回滚。公网12文件逐项哈希通过；入口index-Dhi4Gg-W.js、index-zyShRi34.css，index SHA256 007bff5f8e4216c0ee3877933bf3984ae172e09b1b47209bd7dfe347212cb330。
真实云站https://43.161.223.91/的Edge验收23项通过，42个API请求全部200，无控制台/页面错误，桌面及390/320截图通过，筛选展开/选择保留/光标/开关持久化/键盘/减少动态/触屏/强制配色正常。后端容器ID、镜像和启动时间不变；142条任务逻辑哈希883f4340aabfcef5fb505f1c3109ed9faeb9ae5e785cb8e39bb2df4edbaa75e3不变；日更镜像、账本、行情指针、timer配置保持。10月15日07:30账本scheduled/succeeded、目标10月14日，下一次10月16日07:30。
Pages路径与HTTPS API构建通过，候选入口index-kBBHay7A.js；Pages尚待main合并及正式验收，不能当作已上线。现环境有SSH推送权限，无GitHub API令牌或gh，main受保护；请创建并合并https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/cr068-ui-motion 。实际云端证据在原仓库ignored artifacts/cr068-ui/deployment.json、cloud-browser.json、cloud-desktop.png、cloud-filters.png、cloud-mobile-390/320.png。复现：node artifacts/cr068-ui/online-browser.cjs https://43.161.223.91/ 。未重训、未创建真实回测任务、未上传行情/密钥/任务库。

### CR068 GitHub Pages 正式验收完成（2026-10-15）
PR #50已合并，main提交52b74981a6fe313e671dd41595cc5aab5917590f；[Pages工作流38678433766](https://github.com/why621/intelligent-quant-analysis-platform/actions/runs/38678433766)状态completed/success，11:52:05（北京时间）完成，对应同一合并提交。实际Pages入口引用index-kBBHay7A.js、index-C8W46LFj.css，与本地Pages构建一致。
真实Pages页面Edge验收23项全部通过，42个跨域API响应全部200，无控制台或页面运行错误；覆盖筛选开合/inert/保留选择/搜索、圆环光标/输入与键盘回退、开关持久化、系统减少动态/强制配色/触屏，以及1440桌面、390/320手机布局；已查看桌面和手机截图。仅真实只读请求（GET和数据能力预检POST），没有响应替换或创建回测任务。
证据位于原仓库ignored artifacts/cr068-ui/pages-browser.json、pages-desktop.png、pages-filters.png、pages-mobile-390.png、pages-mobile-320.png；复现命令：node artifacts/cr068-ui/online-browser.cjs https://why621.github.io/intelligent-quant-analysis-platform/ 。本轮仅验收及文档回写，未重复云端部署、训练或采集；无接口契约变化。云站与Pages的CR068功能均已上线，先前“等待合并/验收”为发布过程历史状态。最终文档分支codex/cr068-pages-evidence，不影响已发布功能。
