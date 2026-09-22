# CR051 资产分类筛选优化

日期：2026-09-22。基线main a47d9a5，分支codex/asset-category-filter-20260922。用户要求选择或搜索“半导体”即可筛出相关公司。本轮实现共享选择器，影响相关性、回测、配置三个现有入口；不改研究接口、模型或计算结果。

## 已实现

- 新增半导体、银行、证券、医药医疗、主要消费、新能源六类复选框；多类取并集，再与股票/ETF及搜索条件取交集。
- 搜索保留名称、代码，新增分类、别名和空白分词；支持“半导体”“芯片”“集成电路”及大小写/全角规范化。
- 股票按完整assetType/exchange/symbol匹配参考指数成分，名称不含行业词也可命中；ETF仅按明确名称关键词匹配，宽基ETF不自动算半导体。
- 显示结果分类标签、匹配数量及重置筛选。重置只清空筛选，不清空已选资产；既有10资产上限、停用与忙碌控制保留。
- 只过滤API已发布目录，绝不把参考指数中的其他股票添加到可交易/回测目录。未分类资产仍可按名称、代码和“全部”查找。

## 分类依据和维护

2026-09-22直接读取中证指数官方公开成分文件，六份内容日期均为2026-09-21。这是常用分类的参考快照，不是完整行业分类或历史时点成员库；“主要消费”仅对应800消费成分，不将所有可选消费行业笼统加入。页面已说明覆盖边界。

| UI分类 | 参考指数 | 文件样本数 | 来源 |
| --- | --- | --- | --- |
| 半导体 | H30184（半导体） | 87 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/H30184cons.xls) |
| 银行 | 399986（中证银行） | 42 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/399986cons.xls) |
| 证券 | 399975（证券公司） | 49 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/399975cons.xls) |
| 医药医疗 | 000933（800医卫） | 70 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000933cons.xls) |
| 主要消费 | 000932（800消费） | 36 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/000932cons.xls) |
| 新能源 | 399808（中证新能） | 80 | [成分文件](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/399808cons.xls) |

ETF采用目录名称中的明确行业词进行快捷分类，不声称ETF持仓与参考指数相同。实现位于apps/frontend/src/dashboard/asset-categories.data.js及asset-filter.js；元数据包含原URL、sourceDate、reviewedAt和完整文件SHA256，可追溯刷新。源码仅保留股票身份列表，无价格、权重、用户数据或原始XLS。新增/更新分类时需重读官方文件，校验日期、指数代码、交易所、唯一代码并同步别名和测试；当前不自动随行情日更，名单调整需人工更新版本。

## 实际验证

1. WSL `npm run test --workspace @intelligent-quant/frontend`：83 passed，其中新增5项覆盖关键词/别名、组合过滤、身份隔离、未知分类、不修改原目录和来源完整性。
2. WSL `npm run build --workspace @intelligent-quant/frontend`：通过，Vite生成生产资源。初次Windows npm受UNC目录限制实际执行0测试且构建失败，不计为通过；改在仓库WSL环境执行上述命令。
3. 本地Edge通过Vite加载实际AssetPicker组件。使用既有300股票目录加3个ETF条目作为UI验证输入（非新的发布池），半导体筛出20股票和1芯片ETF；中芯国际不含行业词亦命中。关键词、别名、分类多选、股票/ETF叠加、已选保留、10项上限、移除后可继续选、无匹配重置、忙碌禁用、键盘空格均通过。
4. 1440/390/320三种宽度，document.scrollWidth等于viewport、无页面横向溢出，pageerror为空。截图已保存；图片查看工具受沙箱限制未能打开，不声称逐像素人工审阅。首次验证页使用无模板编译器的Vue入口未渲染，修正临时测试页后完整重跑通过；生产组件未为此修改。
5. 源码核对App.vue三处均使用同一AssetPicker；本轮未执行完整后端或云端业务回归，未推送/部署。

本地证据位于忽略目录artifacts/cr051-asset-categories：六份原始XLS、提取脚本、browser.cjs、browser.json和三张截图。临时预览HTML在验收后删除，本地服务停止。API契约无变更，分类不随请求发送。

## 状态与下一步

T034a/b/c已完成来源核对、实现、离线测试及本地浏览器验收，T034d完成SDD回写。代码在本地分支，未发布线上。下一步经本次版本的推送/发布授权同步GitHub和部署，再核验线上三个入口；分类更新需随参考成分调整维护。

## 授权发布完成（2026-09-22）

用户随后明确要求“推送上线”，授权本次版本推送和现有服务器发布。前文“未推送/未发布”是本地阶段记录；当前源码8eb2101已推送codex/asset-category-filter-20260922，云端静态网页已更新。[云端入口](https://43.161.223.91/#backtest)。GitHub Pages仅main合并触发，仍需[创建并合并本分支PR](https://github.com/why621/intelligent-quant-analysis-platform/pull/new/codex/asset-category-filter-20260922)，不把云端更新等同Pages更新。

- 发布命令：WSL `VITE_API_BASE_URL=/api npm run build --workspace @intelligent-quant/frontend`通过；`git push -u origin codex/asset-category-filter-20260922`成功。仅打包dist的11个静态文件，303837 bytes，包SHA256 `949e886ca770916f16a66466d0b7e6fec3fdddcc3be16d1a2683720d146bfcdb`，不含权重、行情或数据库。
- 严格SSH核对既有网关只读挂载`/opt/intelligent-quant-cr026-20260910/apps/frontend/dist`；后端及网关healthy、nginx配置检查通过。远端逐文件校验包及内容哈希，检测旧index未变化；先复制新hash资源，再原子替换index，保留旧资源供旧页面使用。
- 备份`/opt/intelligent-quant-cr051-20260922/backup/index.html`，旧index SHA256 `053b0bfbddb1dfe62649e88474b3eb1ce315654bd9de84c611c4e70e4c3eaaa0`；新index SHA256 `7f503261a6a64b04fa21b61440e6e7da0a53eae436ddfa6f683f6acdddb8fbf2`，加载`index-DBjierDA.js`。回退只需从该备份原子恢复入口，旧hash资源完整保留；无需回退数据库或模型。
- 后端镜像保持CR050 `sha256:c4e6fd6da65ee6341daaf1e120f52373db39efca9d2f4143c6a043631fc855fd`，未重启或重建后端、未操作行情和任务库。
- 公网Edge实际访问HTTPS云页面：相关性、回测、配置三个选择器均能搜索“半导体/芯片”、显示中芯国际，分类多选/股票ETF叠加及已选保留通过；各入口半导体筛出21项。1440/390/320均无横向溢出，pageerror为空，`GET /api/health`返回200/ok。
- 首轮验收脚本将所有POST误当写操作；页面选项变化自动触发只读`POST /api/data/capability`。保留首轮记录，核对接口后明确仅允许覆盖检查POST再完整重跑通过；未请求创建回测任务、配置建议或其他写接口。

证据：忽略目录artifacts/cr051-asset-categories下release.json、preflight.sh.log、deploy.sh.log、cloud-browser-first.json、cloud-browser.json及cloud-*.png；远端发布记录`/opt/intelligent-quant-cr051-20260922/deployment.json`。命令为`python -X utf8 artifacts/cr051-asset-categories/upload.py`、`python -X utf8 artifacts/cr040-deploy-20260915/run_remote.py artifacts/cr051-asset-categories/deploy.sh`、`node artifacts/cr051-asset-categories/cloud-browser.cjs`。本轮完成云端发布及公网UI验收；Pages和远端PR CI待合并流程，不重复累计之前83项测试。
