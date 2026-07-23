# 智能量化分析平台 · 前端

Vue 3 + Vite + ECharts 前端应用，用于展示市场概况、资产相关性、策略回测、策略排行和资产配置建议。目前页面使用 mock 数据，后续通过 src/services/api.js 对接后端。

## 开发

在仓库根目录执行：

    npm install
    npm run dev:frontend

构建和预览：

    npm run build:frontend
    npm run preview:frontend

本地后端地址配置：

    cp apps/frontend/.env.example apps/frontend/.env.local

接口契约见仓库根目录 docs/api-contract.md。GitHub Pages 部署由 .github/workflows/deploy-pages.yml 自动完成；Pages 只能运行静态前端。
