# CR-036 广汽停牌导致日更门禁失败修正


## CR-036 完成结果（2026-09-15，本地修正）

原始公告已通过web读取巨潮PDF（2026-049）第1页：正文自09-14开市起停牌、表格起始09-15；已记录两处日期差异，只登记09-14至09-15，不预填未来10个交易日。官方链接：https://static.cninfo.com.cn/finalpage/2026-09-15/1225564444.PDF 。直接下载PDF返回403，未留存PDF或宣称PDF字节哈希；正文读取成功与下载失败分别记录。

仅修改config/trading-events.json，新增stock:SSE:601238 suspension事件，事件总数13。文件6218字节，SHA256=d16b204c88da9ac1fd4b74a3f2fdd148407770bb3517e653b24832caee564c33。没有修改生产算法、官方来源白名单或质量断言。实际241行观测哈希复验通过，缺09-14由gaps变complete_with_exceptions；额外删除09-11行的离线反例仍gaps，确认未放宽未知缺口。

云端原有300股观测及manifest只读复制到本地artifacts/cr036-suspension-20260915/seed（传输压缩2002378字节），fetch设为必抛异常并offline_reclassify=True，重分类结果289 complete/11 complete_with_exceptions、priceCoverageComplete=true、networkRequestsThisRun=0。候选ID=6cab6864615d2948177e1a4a37a7e809fc971a8fa18e67bf62d635c11b9fe936。无新采集、无修改云端失败账本或既有观测。

验证：PYTHONPATH=services/algorithms/src:services/backend/src .venv/bin/python artifacts/cr036-suspension-20260915/verify.py通过；PYTHONPATH=.:services/algorithms/src:services/backend/src .venv/bin/python artifacts/cr036-suspension-20260915/verify_all.py通过（首次缺项目根目录导致导入失败，补路径后完成）；pytest services/algorithms/tests/test_trading_events.py services/algorithms/tests/test_coverage.py -q -o addopts=，29 passed/0.71s。

未完成：云端事件文件尚未安装；09-14 ETF/指数未采集、五模块和发布未执行；不能把股票离线重分类当完整恢复或自动成功日。预算仍3/4、剩1次。下一具体动作仅需将上述已验证事件配置备份安装到43.161.223.91:/opt/intelligent-quant-cr026-20260910/daily-cr028/config/trading-events.json，供既有09-16调度识别09-14/15停牌；此动作不重跑今日、不扩大预算。根AGENTS.md第6条要求当次发布/线上修改授权，本轮用户“继续”按此前诊断与本地修正执行，云安装须明确授权后做。不推送GitHub；源码修正、详细证据和文档均留本地。
