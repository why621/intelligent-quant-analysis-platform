# CR-038：部分发布配套上线（2026-09-15）

## 授权和最终状态

用户明确“更新到线上”。按CR038登记执行Git分支推送、43.161.223.91配套镜像/日更/事件/前端更新以及已有候选发布。云端已上线，严格HTTPS和真实浏览器验证通过；GitHub Pages现有页面已接到新版API，但新界面仍等待受保护main的PR合并，不能把分支上传当Pages部署完成。

云端新版预览：https://43.161.223.91/ 。GitHub Pages：https://why621.github.io/intelligent-quant-analysis-platform/ 。分支codex/partial-publication-cr038；创建PR入口：https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/partial-publication-cr038 。已通过公开API确认该分支尚无PR。main有GitHub GH013的必须PR规则，当前环境无gh/API写入凭据，只有SSH Git推送；未强推或绕过保护。

## 已发布内容与证据

- 初始源码提交a3fef30，发布包78文件、367899字节，SHA256=4977f2c90400890d12f2cd4990b01a8c1d074d84eb8393bd961f412736a6d903；仅源码、事件配置、生产前端构建，不含密钥、任务库或行情。上传/home/ubuntu/quant-cr038-release.tar.gz；逐成员类型/路径/哈希校验后展开/opt/intelligent-quant-cr038-20260915。
- 固定旧镜像d5e15f032e19f9f5343f3dac929cb37e77880b624cc4b4764d955d240345c50c为构建基线，禁网构建quant-mvp-backend:cr038，新摘要sha256:f0b6f98637727ed5821ef0df9af035ddae61c747d0a4d7ea465f8e227c273ec0。先验证新读端兼容原09-11 v1，再创建并验证v2部分候选。
- 部署自查补充：日更候选目录可能落后于人工发布的线上版本，execute现在优先采用日期较新的线上基线。新增专项测试及原日更回归6 passed；修正后daily_publication.py为8043字节，SHA256=38ce0b5d154848c197fff10a1bcfbdb9200d41f79dce43370798fe37ded1b2ce。该文件作为独立校验补丁覆盖暂存包和日更目录，baseline-fix.json记录，原包哈希不用于冒充补丁后哈希。
- 维护哨兵阻止新回测，runner.lock避免与日更并发；在途任务排空后执行SQLite在线一致备份、独立恢复及integrity_check。28条历史任务全部保留，逻辑哈希ff5b22537e294495fdd4e5d9dd2f4c02733786d3d279811582a2f78285c8a3e4。后端新版读取旧v1探针通过后，才原子发布新候选。未执行故障注入，不将既有离线回滚测试称作本次线上回滚实操。
- 后端源文件、compose镜像引用、日更image-id/工具、13条交易事件配置已安装；云端前端先安装带哈希资源再切换index.html。新主资源index-BlBVGFdJ.js、index-DSkZrTFa.css。Nginx配置检查/reload及容器健康检查通过，维护哨兵已清理。
- 新数据版本1f3a8ff2f3a1ce2bfade6ca64d689c62a35719b89c14cd57045ec8be79b67447，目标2026-09-14。300股用云端已有09-14观察（按新停牌事件校验），27ETF和指数保留原线上09-11历史，**未使用本地09-09旧基线覆盖线上数据**。没有新采集或同日重试。
- 云端概览299只可比较股票+1只已核实停牌，缺失指标为null；旧指数不显示为09-14指数。正常股票相关性、两种策略回测、模拟配置在禁网云候选验收通过；排行依赖的510300缺09-14，保持不可用，不冒充全五模块完整通过。

## 线上验收

1. 新后端读取旧v1再读取新v2，均通过版本/327目录/概览分母及计数一致性探针。
2. Windows urllib严格HTTPS访问status/overview，通过同版及09-14批次检查；availability.readyCount=300，510300最后行情09-11，指数stale。
3. 真实Edge访问云新版页面：327资产、正常股票09-14、旧ETF09-11、601238停牌且最后成交09-11显示正确；正常股票相关性实际POST 200；1440/820/390视口无横向溢出，pageerror为空。
4. Edge打开实际GitHub Pages，在该网页上下文跨域调用新版云API：相关性200、正常股票模拟配置200且dataContext一致；含未更新ETF的当前区间请求503。pagesNewUi=false，明确记录Pages界面尚未合并部署。
5. 对发布前备份的全部28个任务逐个读取新线上API，status/request/result完全一致，existingJobsMatched=28。
6. 新日更镜像禁网dry-run返回waiting_new_day、targetDate=09-14。前后原state.json哈希一致：ed004988d2d4ec191671770f04e80d040c55dec5c25f559fe4cb09f734906252。原3次账本不改；预算仍3/4，剩1次。timer active，下一次09-16 07:30 CST，未补跑。
7. 本次基线补丁6项离线回归通过，其中1项新增；此前CR037的431项测试与生产构建证据保留。工作流已纳入发布回归，但新分支本轮尚未PR，未声称GitHub CI成功。

## 备份、命令与后续

云备份根：/opt/intelligent-quant-cr038-20260915/backup；含旧compose、源码、日更工具/镜像引用、事件、HTML、SQLite备份/恢复及promotion旧指针。原镜像tag保留。deployment.json、candidate/validation.json、live-jobs.json、baseline-fix.json保存在同一隔离发布根。

本地artifacts/cr038-deploy-20260915保存prepare.sh/validate.sh/cutover.sh/verify_jobs.sh及实际日志、archive.json、https.json、browser/browser.json、pages-cors.json。执行方式为run_remote.py通过既有严格SSH身份及sudo bash -s运行明确脚本；docker build --network none；候选验证容器--network none；生产通过既有compose更新backend，再用cloud_publication.promote维护/备份/原子切换；浏览器使用Playwright Edge。工具审查曾因通信中断未启动命令，确认未执行后重试成功，无剩余审批阻断。

下一步仅需通过上述入口创建并合并PR，触发既有Pages工作流；合并后核对新资源和Pages资产日期/部分更新UI。云端已更新，不再重复要求同一云上传授权。自动相邻两交易日验收仍待实际调度；本次为人工部分发布，不计完整自动成功日，也未扩大预算。
