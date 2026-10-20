<template>
  <div class="dashboard">
    <header class="topbar">
      <a class="brand" href="#top" aria-label="智能量化分析平台首页">
        <span class="brand-mark">量</span>
        <span><strong>智能量化分析平台</strong><small>A 股与场内 ETF · 次日早晨更新</small></span>
      </a>
      <nav aria-label="研究模块导航">
        <a href="#market">市场概况</a>
        <a href="#correlation">资产相关性</a>
        <a href="#backtest">策略回测</a>
        <a href="#ranking">策略排行</a>
        <a href="#allocation">次日配置</a>
      </nav>
    </header>

    <main id="top" class="content">
      <InterfaceEffects />
      <section class="hero">
        <div class="signal-sweep" aria-hidden="true"><span></span></div>
        <div class="hero-copy">
          <p class="eyebrow">QUANT LAB / 收盘后的策略实验室</p>
          <h1>洞察市场信号，<br /><em>构建你的研究策略。</em></h1>
          <p>
            当前可体验 2–10 个资产相关性、两种传统策略回测、策略排行及模拟配置。
            所有结果仅用于教学研究，不会提交真实订单。
          </p>
          <p class="notice">研究范围：{{ dataStatus.assetCount || assetCatalog.length }} 只资产，批次目标日见右侧，各资产实际末日与缺口见选择列表。
            当前成分固定名单研究存在幸存者偏差；强化学习策略已开放实验回测，长期收益有效性尚未验证。</p>
          <div class="chips">
            <a href="#correlation">开始资产研究 ↗</a><a href="#backtest">策略实验室 →</a>
          </div>
        </div>
        <div class="status-card">
          <div class="status-caption"><span>数据发布状态</span><span>DATA STATUS</span></div>
          <div class="status-line">
            <span :class="['status-dot', dataStatus.status]"></span>
            <strong>{{ connection.loading ? '连接中' : connection.message }}</strong>
          </div>
          <dl>
            <div><dt>发布批次目标日</dt><dd>{{ dataStatus.latestTradeDate || '等待数据' }}</dd></div>
            <div v-if="dataStatus.availability && !dataStatus.availability.complete"><dt>发布状态</dt><dd>部分更新 · 查看资产状态</dd></div>
            <div v-if="dataStatus.availability?.eventMaintenance"><dt>停复牌核验</dt><dd>{{ dataStatus.availability.eventMaintenance.state === 'ready' ? '已核实' : '部分待确认' }}</dd></div>
            <div><dt>资产池</dt><dd>{{ dataStatus.assetCount || assetCatalog.length }} 个</dd></div>
            <div><dt>数据源</dt><dd>{{ dataStatus.source || 'AkShare' }}</dd></div>
            <div><dt>历史行情更新</dt><dd>{{ historyStatusText }}</dd></div>
            <div><dt>市场概览更新</dt><dd>{{ overviewStatusText }}</dd></div>
          </dl>
        </div>
      </section>

      <div v-if="!connection.live && !connection.loading" class="notice">
        <strong>接口联调状态：</strong>{{ connection.message }}。不可用的数据不以随机数或零替代。
      </div>

      <aside class="research-flow" aria-label="研究流程联动">
        <strong>研究工作流</strong><span>市场日期 → 相关性选池 → 回测与组合排行 → 配置重放</span>
        <p>相关性默认同步回测资产与区间，回测同步排行榜全部配置，并默认同步模拟参数和费用。下游手动改选后可恢复跟随；联动只更新草稿，计算需手动提交。</p>
        <p v-if="workflowNotice" role="status">{{ workflowNotice }}</p>
      </aside>

      <section id="market" class="panel">
        <header class="panel-head">
          <div><p>MARKET OVERVIEW</p><h2>市场概况</h2></div>
          <span>{{ market.tradeDate ? `交易日 ${market.tradeDate}` : '等待收盘后日更' }}</span>
        </header>
        <DataCapability :request="{ module: 'overview' }" :version="dataStatus.dataContext?.dataVersion" />
        <button class="secondary" type="button" :disabled="!dataStatus.latestTradeDate || correlationBusy" @click="workflow.usePublishedRange">以本批截止日开始最近一年研究</button>
        <p v-if="assetCatalogError" class="notice" role="alert">{{ assetCatalogError }}</p>
        <p v-if="market.scope" class="notice">当前300成分固定名单 · 有效比较 {{ market.coverage.priced }}/300 · 不含ETF；复权收盘变化与价格指数收益口径不同。</p>
        <p v-if="marketNotice" class="notice" role="status">{{ marketNotice }}</p>
        <div class="market-grid">
          <article class="card">
            <h3>{{ market.scope ? "沪深300成分宽度" : "市场宽度" }}</h3>
            <div class="metric-list">
              <div><span>上涨家数</span><b class="positive">{{ formatInteger(market.advancing) }}</b></div>
              <div><span>下跌家数</span><b class="negative">{{ formatInteger(market.declining) }}</b></div>
              <div><span>平盘家数</span><b>{{ formatInteger(market.unchanged) }}</b></div>
              <div><span>涨停 / 跌停</span><b>{{ formatInteger(market.limitUp) }} / {{ formatInteger(market.limitDown) }}</b></div>
            </div>
          </article>
          <article class="card">
            <h3>{{ market.scope ? "沪深300价格指数" : "主流指数" }}</h3>
            <div class="metric-list">
              <p v-if="!market.indices.length" class="hint">本批次指数暂不可用，其他有效资产仍可研究。</p>
              <div v-for="index in market.indices" :key="index.symbol">
                <span>{{ index.name }}<small>{{ index.symbol }}</small></span>
                <b :class="tone(index.changePct)">
                  {{ formatNumber(index.close) }} · {{ formatPct(index.changePct) }}
                </b>
              </div>
            </div>
          </article>
          <article class="card">
            <h3>资金热度</h3>
            <div class="capital-grid">
              <div><span>{{ market.scope ? "300成分成交额" : "股票成交额" }}</span><strong>{{ formatCny(market.turnoverCny) }}</strong></div>
              <div v-if="!market.scope"><span>北向净流入</span><strong :class="tone(market.northboundNetCny)">
                {{ formatCny(market.northboundNetCny) }}
              </strong></div>
            </div>
            <p class="hint">外部数据源不可用时返回 null，不以 0 冒充真实数值。</p>
          </article>
        </div>
      </section>

      <section id="correlation" class="panel">
        <header class="panel-head">
          <div><p>CORRELATION</p><h2>资产相关性</h2></div>
          <span>收益率口径 · 前复权</span>
        </header>
        <DataCapability :request="{ module: 'correlation', symbols: correlationSymbols, startDate: correlationStartDate, endDate: correlationEndDate }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="correlationBusy" @recover="recoverData('correlation', $event)" @checked="capabilityStates.correlation = $event" />
        <div class="split">
          <article class="card form-card">
            <h3>选择 2–10 个资产</h3>
            <AssetPicker v-model="correlationSymbols" :assets="assetCatalog" label="资产组合" :disabled="correlationBusy" />
            </article>
          <div class="result-stack">
          <article class="card form-card"><h3>研究区间</h3>
<div class="date-row">
              <label>开始日期<input v-model="correlationStartDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" /></label>
              <label>结束日期<input v-model="correlationEndDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" /></label>
            </div>
            <button
              class="primary full"
              type="button"
              :disabled="!correlation.canSubmit.value || correlationBusy || capabilityStates.correlation === 'unavailable'"
              @click="correlation.submit"
            >{{ correlationBusy ? '计算中…' : '计算相关矩阵' }}</button>
            <p class="hint" role="status">{{ correlation.dateNotice.value }}</p>
            <p v-if="correlation.validationError.value" class="hint">{{ correlation.validationError.value }}</p>
            <p v-if="correlationError" class="error">{{ correlationError }}</p>
            <p class="hint">{{ correlationValidSymbols.length }} 个有效代码；矩阵按共同交易日对齐。</p>
          </article>
          <article class="card chart-card">
            <div class="card-head"><h3>相关系数矩阵</h3><span>
              {{ correlationResult ? `${correlationResult.observationCount} 个样本` : '等待计算' }}
              <small v-if="correlationResult?.returnAlignment">相邻共同收盘区间收益（停牌可能跨多日）</small>
              <small v-if="correlationResult?.dataContext">{{ contextLabel(correlationResult.dataContext) }}</small>
            </span></div>
            <p v-if="correlation.resultRequest.value" class="hint">本次结果：{{ correlation.resultRequest.value.symbols.join('、') }} · {{ correlation.resultRequest.value.startDate }} 至 {{ correlation.resultRequest.value.endDate }}</p>
            <p v-if="correlation.resultStale.value" class="notice">选择已变化，下方仍为上一次提交的矩阵；请重新计算。</p>
            <p v-if="correlationResult?.matrix.some(row => row.some(value => value == null))" class="hint">
              部分资产对无有效相关系数，留空显示；未以 0 代替。
            </p>
            <p v-if="chartErrors.correlation" class="error" role="alert">{{ chartErrors.correlation }}</p>
            <div ref="correlationChart" class="chart" :class="{ 'chart-empty': !correlationResult }"></div>
            <div v-if="!correlationResult" class="empty-guide"><span>01 · 选择资产</span><span>02 · 确认共同区间</span><span>03 · 查看相关程度</span></div>
          </article>
          </div>
        </div>
      </section>

      <section id="backtest" class="panel">
        <header class="panel-head">
          <div><p>BACKTEST</p><h2>策略回测</h2></div>
          <span>收盘出信号 · 下一开盘成交</span>
        </header>
        <div class="flow-controls"><span>资产：{{ backtestAssetsLinked ? '跟随相关性' : '单独选择' }} · 日期：{{ backtestDatesLinked ? '跟随相关性' : '单独设置' }}</span><button class="secondary" type="button" :disabled="workflow.backtestLocked.value" @click="workflow.restoreBacktest">恢复跟随相关性</button></div>
        <DataCapability :request="{ module: 'backtest', symbols: backtestSymbols, startDate: backtestStartDate, endDate: backtestEndDate, benchmark: backtest.benchmarkMode.value === 'custom' ? backtestBenchmark : null }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="backtestBusy" @recover="recoverData('backtest', $event)" @checked="capabilityStates.backtest = $event" />
        <div class="split backtest-workspace">
          <article class="card form-card backtest-form">
            <div class="form-section"><p class="group-kicker">01 / 研究标的</p>
              <AssetPicker v-model="backtestSymbols" :assets="assetCatalog" label="回测资产" :disabled="backtestBusy" />
            </div>
            <div class="form-section"><p class="group-kicker">02 / 策略选择</p>
              <StrategyPicker v-model="backtestStrategyId" :strategies="strategies" :disabled="backtestBusy" />
            </div>
            <div class="form-section parameter-section"><p class="group-kicker">03 / 参数与执行</p>
              <label v-for="field in backtest.parameterFields.value" :key="field.key">
              {{ field.label }}
              <select v-if="field.type === 'string'" v-model="backtestParameters[field.key]" :name="field.key" :disabled="backtestBusy">
                <option v-for="choice in field.enum" :key="choice" :value="choice">{{ choice }}</option>
              </select>
              <input v-else v-model.number="backtestParameters[field.key]" type="number"
                :name="field.key" :min="field.minimum" :max="field.maximum"
                :step="field.type === 'integer' ? 1 : 'any'" />
            </label>

            <label>比较基准模式
              <select v-model="backtest.benchmarkMode.value" :disabled="backtestBusy">
                <option value="buy_and_hold">所选资产买入持有（默认）</option>
                <option value="custom">指定指数或 ETF</option>
                <option value="none">无基准（Alpha / Beta 不适用）</option>
              </select>
            </label>
            <label v-if="backtest.benchmarkMode.value === 'custom'">指定比较基准
              <select v-model="backtestBenchmark" :disabled="backtestBusy">
                <option value="">请选择基准</option>
                <option v-for="asset in backtest.benchmarkOptions.value" :key="asset.symbol" :value="asset.symbol">
                  {{ asset.name }} · {{ asset.assetType === 'index' ? '价格指数' : 'ETF' }} · {{ asset.symbol }}
                </option>
              </select>
            </label>
            <p class="hint">默认基准将所选资产初始等权买入后持有，不再平衡、不计费用，展示价格收益。ETF 和价格指数均非全收益口径。</p>
            <p class="hint">{{ backtest.modelContext.value?.portfolioMode === 'joint_portfolio' ? '联合组合模型：同时观察所选资产、输出资产与现金权重，使用唯一共享资金账户。' : backtest.modelContext.value ? '旧单资产模型独立账户，保留已发布执行口径。' : '共享组合账户：所选资产使用同一资金池、现金预留与交易成本。' }}</p>
            <div class="config-grid">
              <label>初始资金（元）<input v-model.number="backtest.initialCapitalCny.value" type="number" min="1" :disabled="backtestBusy" /></label>
              <label>预留现金（%）<input v-model.number="backtest.cashPct.value" type="number" min="0" max="100" :disabled="backtestBusy" /></label>
              <label>佣金（% / 单边）<input v-model.number="backtest.tradingCosts.value.commissionPct" type="number" min="0" step="0.01" :disabled="backtestBusy || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
              <label>滑点（% / 单边）<input v-model.number="backtest.tradingCosts.value.slippagePct" type="number" min="0" step="0.01" :disabled="backtestBusy || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
              <label>印花税口径<select v-model="backtest.tradingCosts.value.stampDutyMode" :disabled="backtestBusy || !!backtest.modelContext.value?.requiredTradingCosts"><option value="asset_date">按资产类型及成交日期</option><option value="fixed">固定卖出费率</option></select></label>
              <label v-if="backtest.tradingCosts.value.stampDutyMode === 'fixed'">卖出印花税（%）<input v-model.number="backtest.tradingCosts.value.stampDutyPct" type="number" min="0" step="0.01" :disabled="backtestBusy || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
            </div>
            <p class="hint">实际提交费用：{{ costsLabel(backtest.effectiveTradingCosts.value) }}。滑点体现在成交价，费用统计另列。<span v-if="backtest.modelContext.value?.requiredTradingCosts">此模型使用固定评估费用且额外预留现金须为 0%。</span><span v-else>费用及预留现金将同步用于组合排行和模拟配置。</span></p>
            <div class="date-row">
              <label>开始日期<input v-model="backtestStartDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" /></label>
              <label>结束日期<input v-model="backtestEndDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" /></label>
            </div>
            <button
              class="primary full"
              type="button"
              :disabled="!backtest.canSubmit.value || capabilityStates.backtest === 'unavailable'"
              @click="backtest.submit"
            >{{ backtestBusy ? '任务运行中…' : '提交异步回测' }}</button>
            <p class="hint" role="status">{{ backtest.dateNotice.value }}</p>
            <p v-if="backtest.validationError.value" class="hint">{{ backtest.validationError.value }}</p>
            <p v-if="backtest.activeJob.value && !backtestBusy" class="hint">已有未结束任务，请恢复查询后再提交新任务。</p>
            <label>恢复任务编号<input v-model.trim="backtestRecoveryId" placeholder="UUID 任务编号" /></label>
            <button class="secondary full" type="button" :disabled="backtestBusy || !backtestRecoveryId"
              @click="backtest.resume">恢复查询</button>
            <p v-if="backtestJob?.dataContext" class="hint">{{ contextLabel(backtestJob.dataContext) }}</p>
            <p v-if="backtestJob" class="hint">任务 {{ backtestJob.jobId }} · {{ backtestJob.status }}</p>
            <p v-if="backtestError" class="error">{{ backtestError }}</p>

            </div>
            <aside v-if="backtest.modelContext.value" class="hint ppo-notice" role="note">
              <strong>{{ backtest.selectedStrategy.value?.name }} · 实验性回测</strong>
              <details class="model-training-assets"><summary>查看训练资产（{{ (backtest.modelContext.value.trainingSymbols || backtest.modelContext.value.symbols).length }} 只 · 前复权）</summary><p>{{ (backtest.modelContext.value.trainingSymbols || backtest.modelContext.value.symbols).join('、') }}</p></details>
              <p v-for="line in modelWindowLines(backtest.modelContext.value)" :key="line">{{ line }}</p>
              <p v-if="backtest.modelContext.value.trainingTradingCosts">训练时成本：{{ costsLabel(backtest.modelContext.value.trainingTradingCosts) }}。</p>
              <p v-for="line in modelScopeLines(backtest.modelContext.value)" :key="line">{{ line }}</p>
              <p>回测须从 {{ backtest.modelContext.value.outOfSampleStartDate }} 起，含预热至少{{ backtest.modelContext.value.minimumBars }}根行情。训练链路可运行不代表长期绩效有效；存在过拟合与幸存者偏差，不代表未来收益。</p>
              <div v-if="backtest.modelContext.value.evaluation" class="joint-evaluation">
                <p>冻结样本外对照（含成本，{{ backtest.modelContext.value.testStartDate }} 至 {{ backtest.modelContext.value.testEndDate }}）：</p>
                <p v-if="backtest.modelContext.value.evaluation.aggregation === 'mean_of_three_independent_10_asset_reference_portfolios'">以下为三组独立十资产参考组合的指标均值；不是当前所选组合的结果。当前组合表现请以实际回测为准。</p>
                <p>模型收益 {{ backtest.modelContext.value.evaluation.test.returnPct.toFixed(2) }}% · 最大回撤 {{ backtest.modelContext.value.evaluation.test.maxDrawdownPct.toFixed(2) }}% · 累计双边换手 {{ backtest.modelContext.value.evaluation.test.turnoverMultiple.toFixed(2) }} 倍。</p>
                <p>等权买入持有收益 {{ backtest.modelContext.value.evaluation.baselines.equal_weight_hold.returnPct.toFixed(2) }}% · 均线目标权重基线收益 {{ backtest.modelContext.value.evaluation.baselines.ma_cross.returnPct.toFixed(2) }}%。</p>
                <p>评估仅覆盖记录的资产样本及历史窗口，不能替代所有组合或长期实盘验证。没有证明长期超额收益。</p>
              </div>
              <button type="button" :disabled="backtestBusy || backtest.activeJob.value || !backtest.canApplyModelRange.value" @click="applyModelRange">使用当前可用样本外日期区间</button>
            </aside>
          </article>
          <article class="card">
            <div class="card-head"><h3>{{ backtest.strategyName.value }}结果</h3><span>
              {{ backtestResult ? '真实回测输出' : '尚未运行' }}
            </span></div>
            <p v-if="backtest.resultStale.value" class="notice">当前草稿已变化，下方仍显示已提交任务的结果，未自动重新回测。</p>
            <p v-if="backtestJob" class="hint">{{ backtest.benchmarkLabel.value }}</p>
            <p v-if="backtestJob?.result?.modelContext" class="hint">实验性模型：{{ backtestJob.result.modelContext.modelRef }} · {{ backtestJob.result.modelContext.portfolioMode === 'joint_portfolio' ? '已使用区间之前历史预热，当前曲线为样本外回放' : `前${backtestJob.result.modelContext.warmupBars}根预热不交易` }}；不代表未来收益。</p>
            <p v-for="line in modelWindowLines(backtestJob?.result?.modelContext)" :key="line" class="hint">{{ line }}</p>
            <p v-for="line in modelScopeLines(backtestJob?.result?.modelContext)" :key="line" class="hint">{{ line }}</p>
            <p v-if="backtestJob?.request" class="hint">
              {{ backtestJob.request.startDate }} 至 {{ backtestJob.request.endDate }} ·
              {{ backtestJob.request.symbols.join('、') }} · 参数 {{ JSON.stringify(backtestJob.request.parameters) }}
            </p>
            <p v-if="backtestJob?.request" class="hint">本次资金 {{ money(backtestJob.request.initialCapitalCny) }} · 预留现金 {{ backtestJob.request.cashPct ?? 0 }}% · {{ costsLabel(backtestJob.request.tradingCosts) }}</p>
            <p v-if="chartErrors.equity" class="error" role="alert">{{ chartErrors.equity }}</p>
            <div ref="equityChart" class="chart" :class="{ 'chart-empty': !backtestResult }"></div>
            <div v-if="!backtestResult" class="empty-guide"><span>配置研究参数</span><span>提交后等待任务完成</span><span>或恢复已有任务编号</span></div>
            <div class="result-grid">
              <div><span>总收益率</span><b>{{ formatPct(backtestMetrics?.totalReturnPct) }}</b></div>
              <div><span>年化收益率</span><b>{{ formatPct(backtestMetrics?.annualizedReturnPct) }}</b></div>
              <div><span>最大回撤</span><b>{{ plainPct(backtestMetrics?.maxDrawdownPct) }}</b></div>
              <div><span>夏普</span><b>{{ formatNumber(backtestMetrics?.sharpe) }}</b></div>
              <div><span>Alpha</span><b>{{ plainPct(backtestMetrics?.alphaPct) }}</b></div>
              <div><span>Beta</span><b>{{ formatNumber(backtestMetrics?.beta) }}</b></div>
            </div>
            <div v-show="backtestResult" class="explanation-panel">
              <h3>交易与成本解释</h3>
              <div class="result-grid">
                <div><span>交易次数（成交笔数）</span><b>{{ backtestResult?.costSummary?.tradeCount ?? backtestResult?.trades?.length ?? '未记录' }}</b></div>
                <div><span>累计费用（佣金 + 税）</span><b>{{ money(backtestResult?.costSummary?.feesCny) }}</b></div>
                <div><span>累计滑点成本</span><b>{{ money(backtestResult?.costSummary?.slippageCny) }}</b></div>
                <div><span>佣金</span><b>{{ money(backtestResult?.costSummary?.commissionCny) }}</b></div>
                <div><span>卖出印花税</span><b>{{ money(backtestResult?.costSummary?.stampDutyCny) }}</b></div>
                <div><span>累计总交易成本</span><b>{{ money(backtestResult?.costSummary?.totalTradingCostCny) }}</b></div>
              </div>
              <p class="hint">净值图三角标记代表实际买卖成交，逐笔记录见下表。总成本 = 费用 + 滑点；基准不计成本。可结合持仓曲线判断空仓和进出时机，不把收益差异直接当作精确归因。</p>
              <p v-if="!backtestResult?.accountCurve?.length" class="hint">该历史任务未记录每日持仓和成本分项，显示“未记录”，不会补造为 0。</p>
              <div ref="exposureChart" class="chart exposure-chart"></div>
              <div v-if="lastAccount" class="hint">期末持仓 {{ plainPct(lastAccount.exposurePct) }} · 现金 {{ money(lastAccount.cashCny) }}；{{ lastAccount.positions.map(item => `${item.symbol} ${plainPct(item.weightPct)}`).join(' / ') || '无资产持仓' }}</div>
              <details class="trade-details"><summary>查看成交明细（{{ backtestResult?.trades?.length || 0 }} 笔）</summary><div class="table-card"><table><thead><tr><th>日期</th><th>资产</th><th>方向</th><th>成交价</th><th>数量</th><th>费用</th><th>滑点成本</th></tr></thead><tbody><tr v-for="(trade, index) in (backtestResult?.trades || [])" :key="index"><td>{{ trade.date }}</td><td>{{ trade.symbol }}</td><td>{{ trade.side === 'buy' ? '买入' : '卖出' }}</td><td>{{ formatNumber(trade.price) }}</td><td>{{ formatNumber(trade.quantity) }}</td><td>{{ money(trade.feeCny) }}</td><td>{{ money(trade.slippageCny) }}</td></tr><tr v-if="!backtestResult?.trades?.length"><td colspan="7">本次没有成交记录。</td></tr></tbody></table></div></details>
            </div>
          </article>
        </div>
      </section>

      <section id="ranking" class="panel">
        <header class="panel-head">
          <div><p>RESEARCH RANKING</p><h2>组合策略排行榜</h2></div>
          <span>跟随当前回测配置 · 手动计算</span>
        </header>
        <div class="ranking-config card">
          <div class="card-head"><h3>当前比较配置</h3><a href="#backtest">调整回测配置 ↑</a></div>
          <p>{{ rankingState.draft.value.symbols.join('、') }} · {{ rankingState.draft.value.startDate }} 至 {{ rankingState.draft.value.endDate }} · 前复权</p>
          <p class="hint">资金 {{ money(rankingState.draft.value.initialCapitalCny) }} · 预留现金 {{ rankingState.draft.value.cashPct }}% · {{ costsLabel(rankingState.draft.value.tradingCosts) }} · {{ rankingBenchmarkLabel(rankingState.draft.value) }}</p>
          <p class="hint">{{ backtest.selectedStrategy.value?.name || rankingState.draft.value.strategyId }}使用当前参数 {{ JSON.stringify(rankingState.draft.value.parameters) }}；其他候选使用各自默认参数，逐项展示。所有入榜策略使用同一资产、日期、资金、费用与基准；不适用策略列出原因。</p>
          <div class="flow-controls"><button class="primary" type="button" :disabled="!rankingState.canSubmit.value" @click="rankingState.submit">{{ rankingBusy ? '正在按配置计算…' : rankingMetadata ? '按当前配置刷新排行' : '按当前配置计算排行' }}</button><span>修改配置不会自动运行回测或重新计算排行。</span></div>
          <p v-if="rankingState.validationError.value" class="hint">{{ rankingState.validationError.value }}</p>
          <p v-if="rankingState.notice.value" class="notice" role="status">{{ rankingState.notice.value }}</p>
          <p v-if="rankingState.error.value" class="error" role="alert">{{ rankingState.error.value }}</p>
        </div>
        <p v-if="rankingState.stale.value" class="notice ranking-stale" role="status">已过期：回测配置、数据批次或模型目录已变化。下方保留上一次结果，请按当前配置刷新后再载入回测。</p>
        <div v-if="rankingMetadata" class="ranking-snapshot">
          <strong>本次结果快照{{ rankingState.stale.value ? '（历史配置）' : '' }}</strong>
          <p>{{ rankingMetadata.request.symbols.join('、') }} · 请求区间 {{ rankingMetadata.request.startDate }} 至 {{ rankingMetadata.request.endDate }} · {{ rankingBenchmarkLabel(rankingMetadata.request) }}</p>
          <p class="hint">实际评价：{{ rankingMetadata.evaluationStartDate }} 至 {{ rankingMetadata.evaluationEndDate }} · {{ rankingMetadata.observationCount }} 个净值观察点</p>
          <p class="hint">资金 {{ money(rankingMetadata.request.initialCapitalCny) }} · 预留现金 {{ rankingMetadata.request.cashPct }}% · {{ costsLabel(rankingMetadata.tradingCosts) }} · 前复权</p>
          <p v-if="rankingMetadata.dataContext" class="hint">{{ contextLabel(rankingMetadata.dataContext) }}</p>
        </div>
        <article class="card table-card ranking-table" :class="{ 'ranking-outdated': rankingState.stale.value }" :aria-busy="rankingBusy">
          <table>
            <thead><tr><th>排名</th><th>策略与参数</th><th>类型</th><th>区间收益</th><th>最大回撤</th><th>夏普</th><th>交易成本</th><th>联动研究</th></tr></thead>
            <tbody>
              <tr v-for="item in ranking" :key="item.strategyId">
                <td>{{ item.rank }}</td><td class="ranking-strategy"><strong>{{ item.strategyName }}</strong><small>参数 {{ JSON.stringify(item.parameters) }}</small><small v-if="item.benchmarkContext">基准：{{ item.benchmarkContext.label }}</small><small v-if="item.modelContext">模型 {{ item.modelContext.modelRef }}</small></td>
                <td>{{ item.category === 'ai' ? 'AI · 实验' : '传统' }}</td>
                <td :class="tone(item.returnPct)">{{ formatPct(item.returnPct) }}</td>
                <td>{{ plainPct(item.maxDrawdownPct) }}</td><td>{{ formatNumber(item.sharpe) }}</td>
                <td>{{ money(item.costSummary?.totalTradingCostCny) }}<small>{{ item.costSummary?.tradeCount ?? '未记录' }} 笔成交</small></td>
                <td><button class="secondary" type="button" :disabled="workflow.backtestLocked.value || rankingState.stale.value || rankingBusy" @click="workflow.loadRanking(item, rankingMetadata)">载入回测</button></td>
              </tr>
              <tr v-if="!ranking.length"><td colspan="8" class="empty">{{ rankingBusy ? '正在计算当前组合的可比结果…' : rankingMetadata ? '当前配置暂无可入榜策略，请查看下方排除原因或调整配置。' : '先确认上方回测配置，再点击“按当前配置计算排行”。' }}</td></tr>
            </tbody>
          </table>
        </article>
        <details v-if="rankingUnavailable.length" class="ranking-exclusions" open><summary>未参与比较的策略（{{ rankingUnavailable.length }}）</summary><p v-for="item in rankingUnavailable" :key="item.strategyId" class="hint"><strong>{{ item.strategyName }}</strong>：{{ item.message }}</p></details>
        <p class="hint">按本区间净收益排序，历史表现不代表未来收益。策略训练范围、预热或执行口径不匹配时会排除，绝不换成其他资产或日期凑榜。</p>
      </section>

      <section id="allocation" class="panel">
        <header class="panel-head">
          <div><p>NEXT-DAY ALLOCATION</p><h2>下一交易日模拟配置</h2></div>
          <span>非实盘 · 不连接券商</span>
        </header>
        <div class="flow-controls"><span>资产：{{ allocationAssetsLinked ? '跟随回测' : '单独选择' }} · 参数 / 费用：{{ allocationConfigLinked ? '与回测共用' : '单独配置' }}</span><button class="secondary" type="button" :disabled="allocationBusy" @click="workflow.restoreAllocation">恢复跟随回测</button><button class="secondary" type="button" :disabled="allocationBusy" @click="allocationConfigLinked = false">单独配置参数</button></div>
        <DataCapability :request="{ module: 'allocation', symbols: allocationSymbols, startDate: allocation.startDate.value || undefined }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="allocationBusy" @recover="recoverData('allocation', $event)" @checked="capabilityStates.allocation = $event" />
        <div class="split allocation-workspace">
          <article class="card form-card">
            <div class="form-section"><p class="group-kicker">研究标的</p><AssetPicker v-model="allocationSymbols" :assets="assetCatalog" label="配置资产" :disabled="allocationBusy" />
            </div></article>
          <div class="result-stack">
          <article class="card form-card"><h3>策略与仓位</h3>
              <p class="hint">从 {{ allocation.startDate.value || '待设置' }} 重放至最新发布交易日，生成其下一交易日目标权重；回测结束日不作为“当前配置”的基准日。</p>
              <StrategyPicker v-model="allocationStrategyId" :strategies="allocation.availableStrategies.value" :disabled="allocationBusy" />
              <p v-if="allocationConfigLinked" class="hint">继承策略：{{ allocation.selectedStrategy.value?.name || allocationStrategyId }} · 参数 {{ JSON.stringify(allocation.parameters.value) }}；需修改共用配置请在回测区修改。</p>
              <div v-if="!allocationConfigLinked" class="config-grid">
                <label v-for="field in allocation.parameterFields.value" :key="field.key">{{ field.label }}<input v-if="field.type !== 'string'" v-model.number="allocation.parameters.value[field.key]" type="number" :min="field.minimum" :max="field.maximum" :step="field.type === 'integer' ? 1 : 'any'" :disabled="allocationBusy" /><select v-else v-model="allocation.parameters.value[field.key]" :disabled="allocationBusy"><option v-for="choice in field.enum" :key="choice" :value="choice">{{ choice }}</option></select></label>
                <label>重放开始日期<input v-model="allocation.startDate.value" type="date" :disabled="allocationBusy" /></label>
                <label>初始资金（元）<input v-model.number="allocation.initialCapitalCny.value" type="number" min="1" :disabled="allocationBusy" /></label>
                <label>佣金（%）<input v-model.number="allocation.tradingCosts.value.commissionPct" type="number" min="0" step="0.01" :disabled="allocationBusy" /></label>
                <label>滑点（%）<input v-model.number="allocation.tradingCosts.value.slippagePct" type="number" min="0" step="0.01" :disabled="allocationBusy" /></label>
                <label>印花税口径<select v-model="allocation.tradingCosts.value.stampDutyMode" :disabled="allocationBusy"><option value="asset_date">按资产及日期</option><option value="fixed">固定卖出费率</option></select></label>
                <label v-if="allocation.tradingCosts.value.stampDutyMode === 'fixed'">卖出印花税（%）<input v-model.number="allocation.tradingCosts.value.stampDutyPct" type="number" min="0" step="0.01" :disabled="allocationBusy" /></label>
              </div>
            <label>预留现金比例（%）<input v-model.number="allocationCashPct" type="number" min="0" max="100" :disabled="allocationBusy || allocationConfigLinked" /></label>
            <p class="hint">资金 {{ money(allocation.initialCapitalCny.value) }} · {{ costsLabel(allocation.tradingCosts.value) }}</p>
            <button
              class="primary full"
              type="button"
              :disabled="!allocation.canSubmit.value || capabilityStates.allocation === 'unavailable'"
              @click="allocation.submit"
            >{{ allocationBusy ? '生成中…' : '生成模拟建议' }}</button>
            <p v-if="allocationError || allocation.validationError.value" class="error">{{ allocationError || allocation.validationError.value }}</p>
            <p class="disclaimer">仅用于教学研究，不构成投资建议，不会提交真实订单。</p>
          </article>
          <article class="card">
            <div class="card-head"><h3>目标权重</h3><span>
              {{ allocationResult ? `${allocationResult.basisDate} → ${allocationResult.targetDate}` : '等待生成' }}
              <small v-if="allocationResult?.dataContext">{{ contextLabel(allocationResult.dataContext) }}</small>
            </span></div>
            <p v-if="allocation.resultStale.value" class="notice">草稿已变化，下方仍是上一次提交的模拟结果，请重新生成。</p>
            <p v-if="allocation.resultRequest.value" class="hint">本次配置：{{ allocation.resultRequest.value.strategyId }} · {{ allocation.resultRequest.value.symbols.join('、') }} · 起点 {{ allocation.resultRequest.value.startDate }} · 参数 {{ JSON.stringify(allocation.resultRequest.value.parameters) }} · {{ costsLabel(allocation.resultRequest.value.tradingCosts) }}</p>
            <p v-if="chartErrors.allocation" class="error" role="alert">{{ chartErrors.allocation }}</p>
            <div ref="allocationChart" class="chart small" :class="{ 'chart-empty': !allocationResult }"></div>
            <div v-if="!allocationResult" class="empty-guide"><span>选择资产与策略</span><span>设置现金比例</span><span>生成模拟权重</span></div>
            <div v-if="allocationResult" class="position-list">
              <div>
                <strong>现金</strong><span>{{ plainPct(allocationResult.cashPct) }}</span>
                <small>实际现金权重（含策略退出后保留的现金）</small>
              </div>
              <div v-for="position in allocationResult.positions" :key="position.symbol">
                <strong>{{ position.symbol }}</strong><span>{{ plainPct(position.weightPct) }}</span>
                <small>{{ actionLabel(position.action) }} · {{ position.reason }}</small>
              </div>
            </div>
          </article>
          </div>
        </div>
      </section>
    </main>

    <footer>© 2026 智能量化分析平台 · 教学科研原型，不构成投资建议</footer>
  </div>
</template>

<script setup>
import { modelWindowLines, modelScopeLines } from './dashboard/model-disclosure.js'
const contextLabel = context => `发布截止 ${context.publicationDate} · 数据 ${context.dataVersion.slice(0, 12)} · 名单 ${context.universeVersion.slice(0, 12)}（${context.consistency === 'published_snapshot' ? '不可变研究批次' : '旧池修订'}）`

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AssetPicker from './components/AssetPicker.vue'
import InterfaceEffects from './components/InterfaceEffects.vue'
import DataCapability from './components/DataCapability.vue'
import StrategyPicker from './components/StrategyPicker.vue'

import { allocationOption, correlationOption, equityOption, exposureOption } from './dashboard/charts'
import { formatNumber, formatPct } from './dashboard/common'
import { useAllocation } from './dashboard/use-allocation'
import { useBacktest } from './dashboard/use-backtest'
import { useCorrelation } from './dashboard/use-correlation'
import { useMarket } from './dashboard/use-market'
import { useRanking } from './dashboard/use-ranking'
import { initialiseDashboard } from './dashboard/startup'
import { useResearchContext } from './dashboard/use-research-context'

const { connection, dataStatus, assetCatalog, market, strategies,
  historyStatusText, overviewStatusText, marketNotice, assetCatalogError, initialise } = useMarket()
const correlation = useCorrelation(dataStatus)
const backtest = useBacktest(strategies, dataStatus, assetCatalog)
const allocation = useAllocation(strategies, undefined, dataStatus, assetCatalog)
const rankingState = useRanking(backtest, dataStatus, strategies)
const { result: rankingMetadata, items: ranking, unavailable: rankingUnavailable, busy: rankingBusy } = rankingState
const workflow = useResearchContext(correlation, backtest, allocation, dataStatus)
const { backtestSymbols, backtestStartDate, backtestEndDate, allocationSymbols, allocationStrategyId,
  backtestAssetsLinked, backtestDatesLinked, allocationAssetsLinked, allocationConfigLinked, notice: workflowNotice } = workflow

const { symbols: correlationSymbols, startDate: correlationStartDate, endDate: correlationEndDate,
  result: correlationResult, busy: correlationBusy, error: correlationError,
  validSymbols: correlationValidSymbols } = correlation
const { strategyId: backtestStrategyId, job: backtestJob, busy: backtestBusy, error: backtestError,
  parameters: backtestParameters, benchmark: backtestBenchmark, recoveryId: backtestRecoveryId } = backtest
const { cashPct: allocationCashPct,
  result: allocationResult, busy: allocationBusy, error: allocationError } = allocation

const capabilityStates = ref({})
function recoverData(module, patch) {
  const form = { correlation, backtest, allocation }[module]
  if (!form || form.busy.value || (module === 'backtest' && backtest.activeJob.value)) return
  if (patch.symbols) {
    if (module === 'backtest') backtestSymbols.value = [...patch.symbols]
    else if (module === 'allocation') allocationSymbols.value = [...patch.symbols]
    else form.symbols.value = [...patch.symbols]
  }
  if (patch.endDate && form.endDate) {
    if (module === 'backtest') backtestEndDate.value = patch.endDate
    else form.endDate.value = patch.endDate
  }
  if ('benchmark' in patch && module === 'backtest') { form.benchmark.value = patch.benchmark || ''; form.benchmarkMode.value = patch.benchmark ? 'custom' : 'buy_and_hold' }
  form.error.value = ''
  if (form.result) form.result.value = null
}

const backtestResult = computed(() => backtestJob.value?.result || null)
const backtestMetrics = computed(() => backtestResult.value?.metrics || null)
const lastAccount = computed(() => backtestResult.value?.accountCurve?.at(-1) || null)
function applyModelRange() {
  backtestDatesLinked.value = false
  if (backtest.modelContext.value?.assetScope !== 'published_universe') backtestAssetsLinked.value = false
  backtest.applyModelRange()
}
const correlationChart = ref(null)
const equityChart = ref(null)
const exposureChart = ref(null)
const allocationChart = ref(null)
const charts = {}
const chartErrors = ref({})
let mounted = false

const formatInteger = (value) => value == null ? '—' : Number(value).toLocaleString('zh-CN')
const formatCny = (value) => value == null ? '—' : `${(Number(value) / 100000000).toFixed(2)} 亿元`
const plainPct = (value) => value == null ? '—' : `${Number(value).toFixed(2)}%`
const tone = (value) => value > 0 ? 'positive' : value < 0 ? 'negative' : ''
const actionLabel = (action) => ({ increase: '增加', hold: '持有', decrease: '降低', exit: '退出' }[action] || action)
const money = value => typeof value === 'number' && Number.isFinite(value) ? `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '未记录'
const rankingBenchmarkLabel = request => request.benchmarkMode === 'buy_and_hold' ? '所选组合初始等权买入持有基准（不计费用）' : request.benchmarkMode === 'custom' ? `自定义基准 ${request.benchmark}` : '无基准'
const costsLabel = costs => costs ? `佣金 ${costs.commissionPct}% / 滑点 ${costs.slippagePct}% / ${costs.stampDutyMode === 'asset_date' ? '印花税按资产及日期（ETF 免税）' : `固定卖出印花税 ${costs.stampDutyPct}%`}` : '费用口径未记录'

const resizeCharts = () => Object.values(charts).forEach((chart) => chart?.resize())

onMounted(async () => {
  mounted = true
  await nextTick()
  if (!mounted) return
  const startChart = async (name, load, create, element, option) => {
    const module = await load()
    if (!mounted) return
    charts[name] = create(module).init(element.value, 'dark')
    charts[name].setOption(option())
  }
  window.addEventListener('resize', resizeCharts)
  await initialiseDashboard(initialise, {
    correlation: () => startChart('correlation', () => import('./lib/echarts-heatmap'),
      module => module.getHeatmapEcharts(), correlationChart, () => correlationOption(correlationResult.value)),
    equity: () => startChart('equity', () => import('./lib/echarts-line'),
      module => module.getLineEcharts(), equityChart, () => equityOption(backtestResult.value)),
    exposure: () => startChart('exposure', () => import('./lib/echarts-line'),
      module => module.getLineEcharts(), exposureChart, () => exposureOption(backtestResult.value)),
    allocation: () => startChart('allocation', () => import('./lib/echarts-pie'),
      module => module.getPieEcharts(), allocationChart, () => allocationOption(allocationResult.value))
  }, name => {
    if (mounted) chartErrors.value[name] = '图表加载失败，请刷新页面重试；已取得的数据和计算结果仍可查看。'
  })
})

watch(correlationResult, (value) => charts.correlation?.setOption(correlationOption(value), true))
watch(backtestResult, (value) => charts.equity?.setOption(equityOption(value), true))
watch(backtestResult, (value) => charts.exposure?.setOption(exposureOption(value), true))
watch(allocationResult, (value) => charts.allocation?.setOption(allocationOption(value), true))

// Empty/result layouts have different heights; resize only after Vue updates the DOM.
watch([correlationResult, backtestResult, allocationResult], async () => {
  await nextTick()
  if (mounted) resizeCharts()
}, { flush: 'post' })

onBeforeUnmount(() => {
  mounted = false
  window.removeEventListener('resize', resizeCharts)
  Object.values(charts).forEach((chart) => chart?.dispose())
})
</script>

<style scoped src="./styles/dashboard.css"></style>
