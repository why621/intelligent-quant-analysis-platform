# 参与开发

本仓库采用模块目录、短期分支和 Pull Request 的协作方式。所有人都可以在 GitHub 网页端上传和编辑文件，但建议较大的代码变更先在本地验证。

## 开始开发

    git clone https://github.com/why621/intelligent-quant-analysis-platform.git
    cd intelligent-quant-analysis-platform
    npm install
    npm run dev:frontend

## 分支命名

- frontend/功能：页面、组件、样式和 API 客户端
- backend/功能：接口、鉴权、数据库和任务编排
- algorithm/功能：数据处理、因子、策略、回测和风控
- docs/主题：文档和接口契约
- fix/问题：跨模块缺陷修复

分支名使用简短的小写英文和连字符，例如 backend/backtest-api。

## 提交和 Pull Request

- 一个提交只处理一个清晰问题，提交信息建议使用 feat:、fix:、docs:、refactor:、test:、chore: 前缀。
- 不直接向 main 推送；使用 Pull Request 合并。
- PR 中说明变更、验证方式、影响模块和接口兼容性。
- 更改 API、字段、枚举或算法输入输出时，同步更新 docs/api-contract.md 或 packages/contracts/。
- 前端变更至少执行 npm run build:frontend。
- 后端和算法模块建立后，应在各自目录增加测试与可重复的依赖锁定方式。

## GitHub 网页端上传

进入目标目录后选择 Add file → Upload files。后端文件放入 services/backend/，算法文件放入 services/algorithms/，共享接口定义放入 packages/contracts/。上传时新建分支并创建 PR，不要把文件散落到仓库根目录。

## 禁止提交

- .env、API Token、SSH 密钥、数据库密码、券商或交易所密钥
- 客户个人信息、账户信息和未脱敏交易记录
- 原始行情大文件、模型权重、回测产物和本地数据库
- node_modules、dist、Python 虚拟环境与缓存

如密钥已经进入提交历史，应立即吊销并轮换；仅删除文件不足以消除泄露风险。
