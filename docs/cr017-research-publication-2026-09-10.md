# CR-017 旧池跨日研究保护（2026-09-10）

本地基线3d8bc3f，保留CR-016六文档修改。已完成首批旧池保护，未部署、未访问行情源、未修改真实行情库；完整T-022仍需T-016j不可变发布。

实现：配置使用已发布截止并检查时效，过期503 DATA_STALE；历史/相关性/排行/配置只读缓存，缺口或含未发布日期的可变缓存拒绝，不补拉；请求前后校验目录/截止/缓存修订，冲突409 DATA_VERSION_CHANGED。API0.5.0返回dataContext，前端研究请求携带读取的版本并显示各结果依据。回测新增可空context_json，提交/执行版本一致，旧完成任务保留，无版本旧待执行任务不能自动重算。

验证：WSL `QUANT_DATA_DIR=artifacts/cr017-test-cache PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python -m pytest services/algorithms/tests services/backend/tests tools -m "not network" -o addopts= -q --tb=short`：336 passed，8 deselected，16.06秒。`node --test --test-reporter=dot apps/frontend/tests/*.test.js`：53通过。WSL `npm run build:frontend`成功，主包index-Tdn91flV.js。Ruff通过。新10项隔离SQLite回归涵盖全局09-07/局部09-08/时钟09-09、拒绝补拉、分项失败、修订更新和排队后跨版。既有算法周末/国庆回归通过。

失败记录：初次针对性测试11项失败为旧fake未声明发布截止，保留检查并补明确状态；第二次101通过/4失败为新增契约字段与无发布状态错误码，已同步后全量通过。Windows npm不支持UNC目录、直接Windows Vite缺Linux依赖对应的Windows绑定；使用已有WSL Node构建成功，未删依赖或锁文件。

限制：legacy_revision并非不可变完整发布。旧可变缓存若更新中/失败或含较新行，保守拒绝；不存在旧完整快照的可靠自动恢复路径。本批不是300池验收，也没有新浏览器/云端/日更证据。下一步CR-018停牌覆盖及研究语义，再有界扩采、指数、完整发布。
