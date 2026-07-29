# GitHub 团队协作流程

## 模块负责人

组员接受仓库邀请后，把真实 GitHub 用户名补充到 `.github/CODEOWNERS`：

| 模块 | 目录 | 建议分支前缀 | GitHub 负责人 |
| --- | --- | --- | --- |
| 前端 | `apps/frontend/` | `frontend/` | 待填写 |
| 后端 | `services/backend/` | `backend/` | 待填写 |
| 算法 | `services/algorithms/` | `algorithm/` | @GhostUling |
| 接口契约 | `packages/contracts/`、`docs/api-contract.md` | `docs/` | 待填写 |

## 每个任务的标准流程

1. 负责人创建 Issue，写清验收条件并分配给组员。
2. 开发者同步 `main`，再从 `main` 创建短期功能分支。
3. 一个分支只解决一个 Issue，提交信息使用约定前缀。
4. 推送功能分支并创建 Pull Request，在描述中填写 `Closes #Issue编号`。
5. 模块负责人 Review，所有 CI 通过且对话解决后合并。
6. 合并后删除功能分支，其他组员再次同步 `main`。

常用命令：

```bash
git switch main
git pull --ff-only origin main
git switch -c backend/health-api

# 完成修改和测试后
git add .
git commit -m "feat: implement health API"
git push -u origin backend/health-api
```

## 首批 Issue 建议

- 前端：把市场概览 mock 数据切换到 `/api/market/overview`，保留加载与失败状态。
- 后端：接入第一个已授权行情数据适配器，替换当前演示数据。
- 算法：为均线交叉回测增加滑点、交易记录和基准收益。
- 契约：把 `docs/api-contract.md` 固化为 OpenAPI/JSON Schema，并加入兼容性检查。

## 合并前检查

- 没有提交 `.env`、Token、真实账户信息或未脱敏交易数据。
- 相关模块测试和 lint 全部通过。
- API 字段变化同步更新契约与调用方。
- 算法结果注明样本区间、费用假设和已知限制。
- PR 至少由一名非作者组员批准。
