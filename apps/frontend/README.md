# 前端应用

`apps/frontend` 是智能量化分析平台的 Vue 3 + Vite 前端，使用 ECharts 展示市场、相关性、回测、策略排行和资产配置结果。

## 已实现功能

- 首页启动时并行读取数据状态、资产列表、市场概览、策略目录和排行。
- 相关性、回测和资产配置页面通过后端 API 获取真实结果。
- 回测任务支持提交、轮询状态和展示指标/资金曲线。
- 后端暂时不可用时，仅使用固定的资产与页面展示兜底；不会随机生成排行、回测或配置结果。
- API 错误、数据过期和更新中状态会在界面中明确提示。

接口字段以 [OpenAPI 契约](../../packages/contracts/openapi.yaml) 为准。

## 本地开发

在仓库根目录执行：

```bash
npm install
cp apps/frontend/.env.example apps/frontend/.env.local
npm run dev:frontend
```

默认访问 `http://localhost:5173`。开发服务器会把 `/api` 代理到 `http://localhost:8000`，因此请同时启动后端。

环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | 浏览器请求的 API 基础路径 |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Vite 开发代理目标 |

跨域部署时，可把 `VITE_API_BASE_URL` 设置为完整后端地址，并在后端 `ALLOWED_ORIGINS` 中加入前端来源。

## 构建检查

```bash
npm run build:frontend
```

## GitHub Pages 说明

Pages 工作流只发布静态前端，无法运行 Flask、SQLite 或后台任务。若未配置公网 API，Pages 页面只能展示不依赖后端的固定内容和“服务不可用”状态。要展示完整业务数据，需要在构建时提供公网 `VITE_API_BASE_URL`，并单独部署后端。
