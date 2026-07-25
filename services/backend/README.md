# Flask 后端接口

本目录提供后端组可直接接手的 Flask 骨架，技术栈为 Python 3.11+、Flask、
AkShare、Pandas。唯一 HTTP 契约是 `packages/contracts/openapi.yaml`。

当前 `/api/health` 可用；其余契约路径均已注册并明确返回
`501 NOT_IMPLEMENTED`：

- 数据状态、资产列表、资产日线、市场概况；
- 策略目录、资产相关性、策略排行；
- 异步回测提交与结果查询；
- 下一交易日模拟配置建议。

组员在 `app/services/` 实现服务并通过装配层注入路由。路由只负责请求解析、校验、
调用和序列化，不直接编写 Pandas 计算，不返回随机占位结果。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/backend[dev]"
quant-backend
```

服务默认位于 `http://127.0.0.1:8000`：

```bash
curl http://127.0.0.1:8000/api/health
ruff check services/backend
pytest services/backend
```

异步回测状态必须遵循 `queued → running → succeeded|failed`。服务器密钥、数据库
密码和真实账户信息只能通过环境变量注入，禁止写入日志、响应或提交历史。
