# 共享契约

这里存放可由前端、后端和算法共同消费的机器可读契约，例如 OpenAPI、JSON Schema、事件消息 Schema 和稳定枚举。

- 当前人工可读接口草案位于 docs/api-contract.md。
- 接口实现稳定后，将 OpenAPI 文件提交到本目录。
- 不兼容字段变更必须经过 Pull Request 评审，并说明迁移策略。
- 自动生成的客户端应标明生成命令，不手工修改生成产物。
