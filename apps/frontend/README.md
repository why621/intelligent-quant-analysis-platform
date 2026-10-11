# 前端应用

`apps/frontend` 是智能量化分析平台的 Vue 3 + Vite 前端，使用 ECharts 展示市场、相关性、回测、策略排行和资产配置结果。

## 已实现功能

- 首页启动时并行读取数据状态、资产列表、市场概览、策略目录和排行。
- 相关性、回测和资产配置页面通过后端 API 获取真实结果。
- 回测任务支持提交、轮询状态和展示指标/资金曲线。
- 后端暂时不可用时，仅使用固定的资产与页面展示兜底；不会随机生成排行、回测或配置结果。
- API 错误、数据过期和更新中状态会在界面中明确提示。

接口字段以 [OpenAPI 契约](../../packages/contracts/openapi.yaml) 为准。

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
