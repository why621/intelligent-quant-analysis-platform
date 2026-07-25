# Flask backend interface

本目录提供后端组可以直接接手的 Flask 接口骨架。技术栈固定为：

- Python 3.11+
- Flask
- AkShare
- Pandas

当前只实现健康检查；市场数据、相关性、回测、策略排行和资产配置端点已经注册，
但会明确返回 `501 NOT_IMPLEMENTED`。组员应在 `app/services/` 中完成服务，再替换
路由里的占位调用。正式接口结构以 `packages/contracts/openapi.yaml` 为准。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "services/backend[dev]"
quant-backend
```

服务默认运行在 `http://127.0.0.1:8000`。

```bash
curl http://127.0.0.1:8000/api/health
```

## 验证

```bash
ruff check services/backend
pytest services/backend
```

不得在服务端日志、响应或提交历史中写入行情供应商密钥、账户信息或真实交易记录。
