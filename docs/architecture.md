# 平台架构与模块边界

## 调用关系

    Browser / GitHub Pages
              │ HTTPS JSON
              ▼
          Backend API
          ├── Database / Cache
          ├── Market data adapter
          └── Algorithm jobs
                 ├── Feature and factor pipeline
                 ├── Strategy and backtesting
                 └── Risk and portfolio optimization

## 边界

- 前端只负责展示、交互和 API 调用，不保存服务端密钥。
- 后端负责认证、授权、输入校验、任务状态、持久化和审计。
- 算法模块负责可重复计算，不依赖 Web 框架。
- contracts 负责共享字段和消息格式，是跨模块变更的评审入口。
- 大型数据和模型使用对象存储或模型仓库，Git 只保存代码、配置模板和小型测试夹具。

## 演进顺序

1. 实现 health 和市场概览接口，完成前后端联调。
2. 抽离当前 mock 数据，通过 API 客户端统一访问。
3. 实现异步回测任务、状态轮询和结果存储。
4. 接入数据源、权限、审计与风险控制。
5. 再考虑实盘交易能力，并要求人工确认和独立风控。
