# CR040 配套上线


## CR040 配套上线（2026-09-15，登记）
用户明确授权“代码推送上线”。推送已验证CR039代码/契约/文档，备份升级既有云后端、日更固定镜像/工具及前端。沿用线上1f3a8ff2行情批次，不重新采集或补造旧采集日志；新assetUpdates/eventMaintenance由后续实际日更生成。现有30任务，state哈希ed004988d2d4ec191671770f04e80d040c55dec5c25f559fe4cb09f734906252。
验收：新镜像禁网读包/模块回归、SSE云端有界只读探测、维护排空/SQLite备份恢复后升级与失败回滚、HTTPS/浏览器/同版预检、任务及账本保留、日更dry-run。四次预算不扩展。遵守main的PR保护，分支推送/云交付和Pages合并分别记录，不将代码升级计为自动交易日成功。逐批回写结果。

## CR040 实际发布结果（2026-09-15）

CR039实现提交2340c56已推送codex/data-maintenance-cr039。云端后端、日更固定镜像/工具、静态前端已配套升级，预览：https://43.161.223.91/。

发布包82文件/378000字节，SHA256 72088c87091f15be969e36086cbf62f628beeead575dff6463518cf5e1977a5e。镜像quant-mvp-backend:cr040，ID sha256:89b150401ffae3a961a68a1b6c8e9e28259644d24eda0adb84bb7e38f180275a；以既有CR038为基底禁网构建。逐文件哈希验证通过，备份在/opt/intelligent-quant-cr040-20260915/backup，维护门控和SQLite备份恢复通过，已准备失败回滚，本次未触发。

切换前后30任务，数据库逻辑SHA256 35aac63e99aef141f6cec1c86744cd8bd7d659eefdc6706d78dfc27f2881fad8一致。行情仍1f3a8ff2f3a1ce2bfade6ca64d689c62a35719b89c14cd57045ec8be79b67447，目标09-14，300股可用、27ETF及指数09-11。未采集或重发行情；旧快照未补造assetUpdates/eventMaintenance，由后续实际日更生成。

云端禁网真实行情：相关性、回测、配置通过，排行依赖510300缺失正确不可用。HTTPS状态/覆盖率/概览契约、7项模块预检Schema及版本一致性通过。Pages来源对新预检接口的OPTIONS/CORS通过。Edge默认连接两次ERR_CONNECTION_CLOSED；禁用代理且严格验证HTTPS证书后，327资产、五预检面板、增加旧ETF后显示510300不可用、移除恢复ready、相关性HTTP200、1440/820/390视口无横向溢出及无页面脚本错误全部通过。证明连接路径差异，尚未定位默认连接关闭的具体根因，保留失败记录。

云端单次SSE官方响应HTTP/结构检查通过：6324字节，SHA256 c72873ba05c093a2efdd71a3aa916257120515b90c3b164e9b48ca4c4eed1ea6，与此前语义验证样本相同。本探测传空资产映射，schemaEvents=0不表示没有停牌；未写事件状态，逐资产语义见CR039离线回放。SZSE/ETF官方自动源、历史缺口自动补齐仍pending。

容器healthy、定时器active，新日更镜像dry-run=waiting_new_day，targetDate=09-14，maxRequestsPerAttempt=1637。账本SHA256 ed004988d2d4ec191671770f04e80d040c55dec5c25f559fe4cb09f734906252未变，预算3/4、剩1次，下一09-16 07:30。人工代码部署不计两实际交易日自动验收，不承诺下次所有数据源成功。

验证命令及证据：artifacts/cr040-deploy-20260915/内run_remote.py分别执行prepare.sh、validate.sh、cutover.sh、source_probe.sh及日志；.venv/bin/python运行check_contracts.py、check_cors.py；Node运行verify_ui.cjs、verify_ui_direct.cjs，browser/browser-retry失败、browser-direct通过。此前501项离线测试及构建见CR039，此次未改实现、不重复计数。

下一步：main受PR保护且当前无GitHub API写凭据；分支已推送，需创建合并 https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/data-maintenance-cr039 后等CI发布Pages，再验Pages五预检UI。云预览已更新，Pages尚不能标记CR039完成。次日真实日更后验新日志和自动维护结果。


### CR040 合并后Pages最终验收（2026-09-15）
PR #24已合并，提交8460d186e643a2faa0cad130f3a27b32326fa099，合并时间08:17:23 UTC。Algorithms、Backend、Frontend、Regression stack CI和Pages发布全部success；Pages运行34946140582，Regression运行34946140596。实际 https://why621.github.io/intelligent-quant-analysis-platform/ 已显示五模块新预检。Edge禁代理直连且正常验证HTTPS证书：327资产、五预检面板、正常股相关性HTTP200、增加510300后明确不可用、移除恢复ready、1440/820/390无横向溢出、无页面脚本错误，通过。
证据：artifacts/cr040-deploy-20260915/merged.json、pages-merged/browser.json及截图；命令为.venv/bin/python artifacts/cr040-deploy-20260915/check_merge.py，以及Node verify_pages.cjs。当前Pages与云端新代码链路已闭环，以上“Pages待合并”仅为历史阶段记录。本次无实现或线上数据修改；实际日更新日志、两实际交易日验收、SZSE/ETF自动官方源等待项不因代码发布通过而标完成。本段为合并后的本地验收回写，尚未另行推送文档提交。
