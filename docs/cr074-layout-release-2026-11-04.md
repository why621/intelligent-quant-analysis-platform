# CR074 页面布局发布记录

### CR074 云站发布完成（2026-11-04）
功能提交48eb9bdeaca76a30ba0bd384194a72852af2777b。执行python tools/deploy_cr074_static.py --revision 48eb9bdeaca76a30ba0bd384194a72852af2777b --output artifacts/cr074-release成功；备份/候选目录/opt/intelligent-quant-cr074-20261104，入口assets/index-Bjn_Bkbg.js，回滚未触发。发布前后160条任务逻辑哈希一致、容器ID/镜像/启动时间、行情指针、日更文件一致，timer active；不等于完整日更回归。
公网命令node tools/verify_cr073_live.cjs https://43.161.223.91/ artifacts/cr074-release/dist-cloud artifacts/cr074-release/cloud-browser，11项通过，包括展开模型说明、旧任务恢复、1440/390/320视口和12文件SHA256一致，0运行错误。未新增任务、未计算模拟、未改生产行情。证据在ignored artifacts/cr074-release/cloud-deployment.json、cloud-browser/report.json及两套build日志。
T-CR074-5云站发布完成；6代码与相关文档通过codex/cr074-page-layout推送，Pages合并/发布验收待完成。main仍10b31ae且受保护，无GitHub API合并凭据；本分支包含未合并CR073完整内容，可直接合并到main。PR入口：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/cr074-page-layout 。合并后以dist-pages独立验收，不能用云站替代Pages。
审批服务连接中断的命令未执行，重试成功；Windows默认GBK读取脚本失败后显式UTF-8修正，语法检查通过。未降低验收标准。长窗、收益和行情缺口不在本轮完成范围。
