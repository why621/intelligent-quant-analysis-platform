# CR-026 HTTPS 与云端最终验收进展（2026-09-10）

## 2026-09-10 续作实际结果（优先于下方准备/阻断历史）

用户已明确同意上传。本批固定包已上传到43.161.223.91，SHA及66文件逐项校验通过，隔离部署到/opt/intelligent-quant-cr026-20260910。新后端镜像构建成功，容器quant-mvp-cr026-backend-1与gateway-1运行；旧镜像/后端/卷保持，旧80前端现代理到新候选提供临时预览：[新包HTTP入口](http://43.161.223.91/)。当前数据截至2026-09-09。

两库SQLite backup与integrity_check通过，备份在隔离根目录backup，候选使用任务副本；实际核对9个旧已完成任务的状态/请求/结果完全保留。尚未演练完整切回旧服务，不能称灾备全验收。

已修复云候选双网络backend别名命中旧50池的问题，代理改唯一容器quant-mvp-cr026-backend-1；nginx -t与327资产/发布版本/概览通过。原始归档不覆盖，部署后代理补丁独立保留。为减少大JS传输问题，启用JS/CSS压缩与临时80代理流式响应，未改变源码/行情哈希。

公网HTTP五模块接口通过，证据artifacts/cr026-cloud-20260910/public-api.json与allocation.json：327目录/覆盖、300概览、10资产123共同区间样本、两策略排行、两策略指数回测、配置同一e5f794c7094c…版本，配置权重合计100%。回测任务5e3382b2-2472-47dd-9e95-479003057e4c及5cc8cbcd-4eb9-435e-97ae-e8d39f191bf4均succeeded。

证书测试环境及正式签发均成功，正式issuer为Let’s Encrypt YE2，SAN为IP43.161.223.91；notBefore 2026-09-10 11:24:13 UTC，notAfter 2026-09-17 03:24:12 UTC。私钥仅留云目录certificates，不下载、不入Git。本机通过将连接地址定向127.0.0.1:443但保留真实IP证书身份的curl验证，327状态200；0.0.0.0及IPv6的443已监听。此验证不是公网443可用证明。

公网443两次连接超时，尚未完成TLS握手，已通过异步问题请用户在腾讯云轻量防火墙放行TCP443。当前只有SSH权限，未获得云控制台/API权限，未修改该层规则。不能把失败握手时curl的默认verify_result=0记为证书公网验证通过。

系统定时器quant-cr026-certificate.timer已启用，每日03/15点加最多30分钟随机延迟，Persistent=true；锁与240秒上限，官方Certbot镜像固定摘要c23159d30afdd9c97960578aa4654f5901de6cae394958f894074dedd55e599d。首次服务Result=success/ExecMainStatus=0；renew --dry-run测试CA实际验证成功、nginx重载通过，证书至少48小时有效期检查通过。正常首次检查因证书新签发而无需续期，不冒充正式续签；未来续期依赖80挑战路由与定时器健康，重建旧80前端须保留本批路由。

Pages Origin https://why621.github.io 的OPTIONS预检返回200，精确Allow-Origin及X-Research-Version等允许头正确。GitHub Pages仍为旧构建，未推送或更新Pages；正式Pages跨域浏览器验收未完成。

浏览器分层记录：普通公网Edge加载成功并显示327资产、09-09截止、完整概览，截图startup-r2.png；完整验收脚本多次遭遇大图表JS的ERR_CONTENT_LENGTH_MISMATCH/ERR_INCOMPLETE_CHUNKED_ENCODING、一次导航网络失败或资源502，未完成全场景。服务器对应记录未见相同502（有客户端中断499），不武断归因服务端/本机网络。错误证据artifacts/cr026-http-browser-20260910/failure.json保留。不能用独立API通过代替该浏览器未通过项，公网HTTPS也尚未验收。

本地新增部署工具Ruff通过，2项隔离/TLS配置检查通过，各实际执行的nginx -t通过；算法代码未变，原375/前端54结果仅作上一批证据，不冒充本轮重跑。下一步：用户放行公网443后验证默认受信任TLS并完成浏览器重测，再协调Pages正式发布。CR-025真实两日自动更新仍独立待验；本批云包固定09-09，未自动同步未来本地日更包。


本批完成只读云核查和可审阅的隔离发布准备；上传被自动审批明确拒绝，未执行部署、签发证书、开443服务或Pages更新。HTTPS与最终云验收保持未完成。

## 已核实

- 严格SSH使用既有known_hosts/HostKeyAlias及用户指定密钥完成身份校验；没有关闭主机验证或输出私钥。
- 云主机43.161.223.91，项目/opt/intelligent-quant-regression，HEAD af02f826b7dcfd1b8a4fb9fd8bdcf56fe07b8d56，工作区无修改，两容器healthy，API health200。80对外、8000仅回环，443未监听，主机ufw inactive；未据此推断云安全组允许443。
- 旧后端镜像a2bd5590d0f66ef9b23ec2c6a61d5fd056620fd71d4ca4c39122fc4491656ef4，前端378d4c56f9ffcd6d042f7ee86f161543f8e3263db0027ff33f45064187d80424。
- GitHub Pages当前返回200，但最新已发布构建是09-04的8a8973a8d142884ed56715549606eb62e3457703，不能视为新327包已上线；当前SSH云版本也仍为CR-015。
- 未发现后端域名配置，已询问用户；官方现已提供公网IP证书路径。Certbot>=5.4支持webroot/standalone申请IP证书，六天有效期必须自动续期及reload。[Let’s Encrypt官方说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)。此处只确认方案，没有声称签发成功。

## 可审阅发布物与门禁

部署配置在deploy/mvp：独立quant-mvp-cr026项目，旧服务与数据卷不覆盖；发布只读挂载，任务库使用备份副本。后端1进程/2线程、1GiB/1.5CPU；精确允许https://why621.github.io和https://43.161.223.91，包含X-Research-Version预检。代理64KiB请求体、每IP与全局回测频率/并发限制；可信证书文件不存在时不加载TLS配置，不创建自签证书。

原始包 artifacts/cr026-cloud-20260910/release.tar.gz，2305993字节，66文件，SHA256 694d5b4f96491cedfaf60be35bf386ddfa478e0833e3e9c658afb38b0e3ca052。包含两模块Python源码、已构建前端、明确六个部署配置，以及CR-024的current.json/不可变327行情发布包；不包含私钥、账户材料、旧数据库或整个artifacts。真实行情只准备传至用户既有云主机，不进入GitHub。

目标暂存 /home/ubuntu/quant-cr026-release.tar.gz；隔离安装 /opt/intelligent-quant-cr026-20260910。tools/cr026_cloud_prepare.sh先检查云HEAD/两个旧镜像ID、包SHA、每文件SHA、路径/文件类型，再创建新目录、SQLite backup副本并integrity_check，随后构建候选；旧服务保持。脚本尚未在云执行，备份也尚未生成，不能记为恢复通过。

离线验证：tools/test_cr026_release.py的2项隔离/TLS配置检查通过；bash -n tools/cr026_cloud_prepare.sh通过；git diff --check通过。初次Ruff发现导入格式和显式check缺失，已修正后复验。配置语义检查不替代真实nginx -t、证书签发、候选五模块或浏览器验收。

## 阻断与下一步

自动审批拒绝SCP上传的原文原因：『该命令将包含内部源代码和发布数据快照的归档上传到云主机；用户虽授权云端验收，但未在可信内容中明确授权这一具体敏感载荷及该目的地的外传。』上传未执行，未通过其他方式绕过。

需要用户明确允许上述源码/构建产物/327快照上传至43.161.223.91的两个具体目录并继续本批隔离部署。获准后先上传及云候选验证，随后完成IP或用户域名证书的staging/正式签发、续期演练、443公网验证，再协调GitHub Pages新前端与精确CORS，真实浏览器五模块/恢复/故障验收。GitHub控制权限、证书实际签发和云安全组仍需实测，不能预判通过。两交易日自动更新保留CR-025，不与本批混淆。
