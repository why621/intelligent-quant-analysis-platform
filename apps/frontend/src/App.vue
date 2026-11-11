<template>
  <div class="dashboard">
    <a class="skip-link" :href="`#${activeTab}`" @click.prevent="focusPanel">跳到当前研究模块</a>
    <header class="topbar">
      <a class="brand" href="#" aria-label="智能量化分析平台首页" @click.prevent="selectTab('market')">
        <span class="brand-mark">量</span>
        <span><strong>智能量化分析平台</strong><small>A 股与场内 ETF · 次日早晨更新</small></span>
      </a>
      <nav class="tabs" role="tablist" aria-label="研究模块">
        <button
          v-for="(tab, index) in tabs"
          :id="`tab-${tab.id}`"
          :key="tab.id"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.id"
          :aria-controls="tab.id"
          :tabindex="activeTab === tab.id ? 0 : -1"
          :class="{ 'is-active': activeTab === tab.id }"
          @click="selectTab(tab.id)"
          @keydown="handleTabKey($event, index)"
        >{{ tab.label }}</button>
      </nav>
      <button
        type="button"
        class="theme-toggle"
        :aria-pressed="isLightTheme"
        @click="toggleTheme"
      ><span class="theme-glyph" aria-hidden="true">{{ isLightTheme ? '☀' : '☾' }}</span>主题 {{ isLightTheme ? '浅色' : '深色' }}</button>
      <details class="display-settings"><summary>显示设置</summary><InterfaceEffects /></details>
    </header>

    <main id="top" class="content">
      <div v-if="!connection.live && !connection.loading" class="notice connection-status">
        <div class="connection-actions">
          <span><strong>数据连接</strong> · {{ connection.message }}。缺失值显示为“—”。</span>
          <button class="secondary" type="button" :disabled="workflow.backtestLocked.value" @click="initialise">重新连接</button>
        </div>
        <details class="connection-diagnostics">
          <summary>连接检查详情</summary>
          <p>数据服务地址：<code>{{ apiBaseUrl }}</code></p>
          <ul>
            <li v-for="item in interfaceStatus" :key="item.id">
              <strong>{{ item.label }}</strong> <code>{{ item.path }}</code>
              <span> · {{ item.message }}</span> <small v-if="item.code">{{ item.code }}</small>
            </li>
          </ul>
          <p v-if="interfaceStatus.some(item => item.code === 'NETWORK_ERROR')">浏览器未提供具体的连接失败原因，需结合证书和跨域检查定位。重新加载无法修复服务端配置。</p>
        </details>
      </div>

      <section class="hero" v-show="activeTab === 'market'">
        <div class="hero-copy">
          <h1>市场与策略研究</h1>
          <p>研究 A 股和场内 ETF 的相关性、策略表现与模拟权重。仅用于教学研究。</p>
          <div class="hero-actions">
            <button type="button" class="hero-cta" @click="selectTab('correlation')">开始资产研究 ↗</button>
            <details class="hero-details">
              <summary>研究范围与限制</summary>
              <p>当前成分固定名单存在幸存者偏差。强化学习策略仅用于实验回测，长期收益有效性尚未验证。实际行情末日与缺口见资产列表。</p>
            </details>
          </div>
        </div>
        <div class="status-card" :aria-busy="connection.loading">
          <strong>数据发布</strong>
          <span v-if="connection.live || connection.loading" class="publication-status">{{ connection.loading ? '连接中…' : connection.message }}</span>
          <dl>
            <div><dt>批次目标日</dt><dd>{{ dataStatus.latestTradeDate || '—' }}</dd></div>
            <div><dt>资产池</dt><dd>{{ dataStatus.assetCount ?? (assetCatalog.length || '—') }}</dd></div>
            <div><dt>历史行情</dt><dd>{{ historyStatusText }}</dd></div>
            <div><dt>市场概览</dt><dd>{{ overviewStatusText }}</dd></div>
          </dl>
          <p v-if="dataStatus.availability && !dataStatus.availability.complete" class="hint">部分更新 · 查看资产状态</p>
          <details v-if="dataStatus.source || dataStatus.availability?.eventMaintenance" class="publication-details">
            <summary>发布详情</summary>
            <p v-if="dataStatus.source" class="hint">数据源：{{ dataStatus.source }}</p>
            <p v-if="dataStatus.availability?.eventMaintenance" class="hint">停复牌核验：{{ dataStatus.availability.eventMaintenance.state === 'ready' ? '已核实' : '部分待确认' }}</p>
          </details>
        </div>
      </section>

      <nav class="research-flow" aria-label="研究流程联动" v-show="activeTab === 'market'">
        <strong>研究流程</strong>
        <button class="link-btn" type="button" @click="selectTab('correlation')">相关性选池</button>
        <button class="link-btn" type="button" @click="selectTab('backtest')">策略回测</button>
        <button class="link-btn" type="button" @click="selectTab('ranking')">组合排行</button>
        <button class="link-btn" type="button" @click="selectTab('allocation')">配置重放</button>
        <details>
          <summary>联动说明</summary>
          <p>相关性资产与区间默认同步到回测。排行资产可独立选择，其余配置继承回测。次日配置默认跟随回测的资产、参数和费用。联动只更新草稿，计算需手动提交。</p>
        </details>
      </nav>
      <p v-if="workflowNotice" class="notice workflow-notice" role="status">{{ workflowNotice }}</p>

      <section id="market" class="panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-market" v-show="activeTab === 'market'">
        <header class="panel-head">
          <div><h2>市场概况</h2></div>
          <span>{{ market.tradeDate ? `交易日 ${market.tradeDate}` : '等待收盘后日更' }}</span>
        </header>
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
            <h3>成交活跃度</h3>
            <div class="capital-grid">
              <div><span>{{ market.scope ? "300成分成交额" : "股票成交额" }}</span><strong>{{ formatCny(market.turnoverCny) }}</strong></div>
              <div v-if="!market.scope"><span>北向净流入</span><strong :class="tone(market.northboundNetCny)">
                {{ formatCny(market.northboundNetCny) }}
              </strong></div>
            </div>
            <p class="hint">成交额反映交易活跃度，不代表资金净流入；暂缺指标显示为“—”。</p>
          </article>
        </div>
        <p v-if="market.scope" class="hint">当前300成分固定名单 · 有效比较 {{ market.coverage.priced }}/300 · 不含ETF；复权收盘变化与价格指数收益口径不同。</p>
        <p v-if="marketNotice && (connection.live || market.tradeDate)" class="notice" role="status">{{ marketNotice }}</p>
        <div class="panel-tools">
          <DataCapability :active="activeTab === 'market' && !connection.loading" :request="{ module: 'overview' }" :version="dataStatus.dataContext?.dataVersion" />
          <button class="secondary" type="button" :disabled="!dataStatus.latestTradeDate || correlationBusy" @click="workflow.usePublishedRange">以本批截止日开始最近一年研究</button>
        </div>
      </section>

      <section id="correlation" class="panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-correlation" v-show="activeTab === 'correlation'">
        <header class="panel-head">
          <div>
            <h2>资产相关性</h2>
            <p v-if="activeTab === 'correlation'" class="context-summary">{{ workspaceSummary }} · {{ workspaceResultState }}</p>
          </div>
          <span>收益率口径 · 前复权</span>
        </header>
        <DataCapability :active="activeTab === 'correlation' && !connection.loading" :request="{ module: 'correlation', symbols: correlationSymbols, startDate: correlationStartDate, endDate: correlationEndDate }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="correlationBusy" @recover="recoverData('correlation', $event)" @checked="capabilityStates.correlation = $event" />
        <div class="split">
          <div class="form-stack">
            <article class="card form-card">
              <AssetPicker v-model="correlationSymbols" :assets="assetCatalog" :loading="connection.loading" :error="assetCatalogError" label="资产组合（2–10 只）" :disabled="correlationBusy" />
            </article>
            <article class="card form-card"><h3>研究区间</h3>
              <div class="date-row">
                <label>开始日期<input v-model="correlationStartDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" :disabled="correlationBusy" /></label>
                <label>结束日期<input v-model="correlationEndDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" :disabled="correlationBusy" /></label>
              </div>
              <button
                class="primary full"
                type="button"
                :disabled="!correlation.canSubmit.value || correlationBusy || capabilityStates.correlation === 'unavailable'"
                @click="correlation.submit"
              >{{ correlationBusy ? '计算中…' : '计算相关矩阵' }}</button>
              <p class="hint" role="status">{{ correlation.validationError.value || (capabilityStates.correlation === 'unavailable' ? coverageWarning : correlation.dateNotice.value) }}</p>
              <p v-if="correlationError" class="error" role="alert">{{ correlationError }}{{ correlationResult ? '；本次未更新，已保留上一次成功结果。' : '' }}</p>
              <p class="hint">已输入 {{ correlationValidSymbols.length }} 个不同代码；矩阵按共同区间对齐。</p>
            </article>
          </div>
          <article class="card chart-card" :aria-busy="correlationBusy">
            <p v-if="correlationBusy" class="notice" role="status">正在更新相关性…{{ correlationResult ? '下方保留上一次结果。' : '结果完成后将显示在这里。' }}</p>
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
            <div v-show="correlationResult" ref="correlationChart" class="chart"></div>
            <p v-if="!correlationResult" class="result-placeholder" :class="{ 'reserves-chart': correlationBusy }">
              {{ correlationBusy ? '正在计算相关矩阵…' : '选定资产和研究区间后，计算相关矩阵。' }}
            </p>
          </article>
        </div>
      </section>

      <section id="backtest" class="panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-backtest" v-show="activeTab === 'backtest'">
        <header class="panel-head">
          <div>
            <h2>策略回测</h2>
            <p v-if="activeTab === 'backtest'" class="context-summary">{{ workspaceSummary }} · {{ workspaceResultState }}</p>
          </div>
          <span>收盘出信号 · 下一开盘成交</span>
        </header>
        <div class="flow-controls"><span>日期：{{ backtestDatesLinked ? '跟随相关性' : '单独设置' }}</span><button class="secondary" type="button" :disabled="workflow.backtestLocked.value" @click="workflow.restoreBacktest">恢复跟随相关性</button></div>
        <DataCapability :active="activeTab === 'backtest' && !connection.loading" :request="{ module: 'backtest', symbols: backtestSymbols, startDate: backtestStartDate, endDate: backtestEndDate, benchmark: backtest.benchmarkMode.value === 'custom' ? backtestBenchmark : null }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="workflow.backtestLocked.value" @recover="recoverData('backtest', $event)" @checked="capabilityStates.backtest = $event" />
        <div class="split backtest-workspace">
          <article class="card form-card backtest-form">
            <div class="form-section"><p class="group-kicker">研究标的</p>
              <AssetPicker v-model="backtestSymbols" :assets="assetCatalog" :loading="connection.loading" :error="assetCatalogError" label="回测资产" :disabled="workflow.backtestLocked.value" />
            </div>
            <div class="form-section strategy-section"><p class="group-kicker">策略与参数</p>
              <StrategyPicker v-model="backtestStrategyId" :strategies="strategies" :disabled="workflow.backtestLocked.value" />
              <div class="strategy-parameters" aria-label="策略参数">
                <label v-for="field in backtest.parameterFields.value" :key="field.key">
                  {{ field.label }}
                  <select v-if="field.type === 'string'" v-model="backtestParameters[field.key]" :name="field.key" :disabled="workflow.backtestLocked.value">
                    <option v-for="choice in field.enum" :key="choice" :value="choice">{{ choice }}</option>
                  </select>
                  <input v-else v-model.number="backtestParameters[field.key]" type="number"
                    :name="field.key" :min="field.minimum" :max="field.maximum"
                    :step="field.type === 'integer' ? 1 : 'any'" :disabled="workflow.backtestLocked.value" />
                </label>
              </div>
              <label>比较基准模式
                <select v-model="backtest.benchmarkMode.value" :disabled="workflow.backtestLocked.value">
                  <option value="buy_and_hold">所选资产买入持有（默认）</option>
                  <option value="custom">指定指数或 ETF</option>
                  <option value="none">无基准（Alpha / Beta 不适用）</option>
                </select>
              </label>
              <label v-if="backtest.benchmarkMode.value === 'custom'">指定比较基准
                <select v-model="backtestBenchmark" :disabled="workflow.backtestLocked.value">
                  <option value="">请选择基准</option>
                  <option v-for="asset in backtest.benchmarkOptions.value" :key="asset.symbol" :value="asset.symbol">
                    {{ asset.name }} · {{ asset.assetType === 'index' ? '价格指数' : 'ETF' }} · {{ asset.symbol }}
                  </option>
                </select>
              </label>
              <details class="inline-details">
                <summary>基准收益口径</summary>
                <p class="hint">默认基准按初始等权买入后持有，不再平衡、不计费用，展示价格收益。ETF 和价格指数均非全收益口径。</p>
              </details>
              <p class="hint">{{ backtest.modelContext.value?.portfolioMode === 'joint_portfolio' ? '联合组合模型：同时观察所选资产、输出资产与现金权重，使用唯一共享资金账户。' : backtest.modelContext.value ? '旧单资产模型独立账户，保留已发布执行口径。' : '共享组合账户：所选资产使用同一资金池、现金预留与交易成本。' }}</p>
            </div>
            <div class="form-section parameter-section"><p class="group-kicker">执行与资金</p>
            <div class="config-grid">
              <label>初始资金（元）<input v-model.number="backtest.initialCapitalCny.value" type="number" min="1" :disabled="workflow.backtestLocked.value" /></label>
              <label>预留现金（%）<input v-model.number="backtest.cashPct.value" type="number" min="0" max="100" :disabled="workflow.backtestLocked.value" /></label>
              <label>开始日期<input v-model="backtestStartDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" :disabled="workflow.backtestLocked.value" /></label>
              <label>结束日期<input v-model="backtestEndDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" :disabled="workflow.backtestLocked.value" /></label>
            </div>
            <details class="advanced-settings"><summary>交易费用与税费设置</summary><div class="config-grid">
              <label>佣金（% / 单边）<input v-model.number="backtest.tradingCosts.value.commissionPct" type="number" min="0" step="0.01" :disabled="workflow.backtestLocked.value || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
              <label>滑点（% / 单边）<input v-model.number="backtest.tradingCosts.value.slippagePct" type="number" min="0" step="0.01" :disabled="workflow.backtestLocked.value || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
              <label>印花税口径<select v-model="backtest.tradingCosts.value.stampDutyMode" :disabled="workflow.backtestLocked.value || !!backtest.modelContext.value?.requiredTradingCosts"><option value="asset_date">按资产类型及成交日期</option><option value="fixed">固定卖出费率</option></select></label>
              <label v-if="backtest.tradingCosts.value.stampDutyMode === 'fixed'">卖出印花税（%）<input v-model.number="backtest.tradingCosts.value.stampDutyPct" type="number" min="0" step="0.01" :disabled="workflow.backtestLocked.value || !!backtest.modelContext.value?.requiredTradingCosts" /></label>
            </div></details>
            <p class="hint">实际提交费用：{{ costsLabel(backtest.effectiveTradingCosts.value) }}。滑点体现在成交价，费用统计另列。<span v-if="backtest.modelContext.value?.requiredTradingCosts">此模型使用固定评估费用且额外预留现金须为 0%。</span><span v-else>费用及预留现金将同步用于组合排行和模拟配置。</span></p>
            <div class="run-bar">
              <button
                class="primary run-submit"
                type="button"
                :disabled="!backtest.canSubmit.value || capabilityStates.backtest === 'unavailable'"
                @click="backtest.submit"
              >{{ backtestBusy ? '任务运行中…' : '开始回测' }}</button>
              <p v-if="backtest.activeJob.value && !backtestBusy" class="hint" role="status">已有未结束任务，请恢复查询后再提交。</p>
              <p v-else class="hint" role="status">{{ backtest.validationError.value || (capabilityStates.backtest === 'unavailable' ? coverageWarning : backtest.dateNotice.value) }}</p>
            </div>
            <details class="task-recovery" :open="!!backtest.activeJob.value">
              <summary>恢复历史任务</summary>
              <div class="resume-bar">
                <label>任务编号<input v-model.trim="backtestRecoveryId" placeholder="UUID 任务编号" /></label>
                <button class="secondary" type="button" :disabled="backtestBusy || !backtestRecoveryId"
                  @click="backtest.resume">恢复查询</button>
              </div>
            </details>
            <p v-if="backtestJob?.dataContext" class="hint">{{ contextLabel(backtestJob.dataContext) }}</p>
            <p v-if="backtestJob" class="hint">任务 {{ backtestJob.jobId }} · {{ jobStatusLabel(backtestJob.status) }}</p>
            <p v-if="backtestError" class="error" role="alert">{{ backtestError }}</p>

            </div>
            <aside v-if="backtest.modelContext.value" class="hint ppo-notice" role="note">
              <strong>{{ backtest.selectedStrategy.value?.name }} · 实验性回测</strong>
              <details class="model-reference"><summary>训练记录与模型适用范围</summary><details class="model-training-assets"><summary>查看训练资产（{{ (backtest.modelContext.value.trainingSymbols || backtest.modelContext.value.symbols).length }} 只 · 前复权）</summary><p>{{ (backtest.modelContext.value.trainingSymbols || backtest.modelContext.value.symbols).join('、') }}</p></details>
              <p v-for="line in modelWindowLines(backtest.modelContext.value)" :key="line">{{ line }}</p>
              <p v-if="backtest.modelContext.value.trainingTradingCosts">训练时成本：{{ costsLabel(backtest.modelContext.value.trainingTradingCosts) }}。</p>
              <p v-for="line in modelScopeLines(backtest.modelContext.value)" :key="line">{{ line }}</p>
              </details>
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
          <article class="card" :aria-busy="backtestBusy">
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
              {{ backtestJob.request.symbols.join('、') }} · 参数 {{ formatParameters(backtestJob.request.parameters) }}
            </p>
            <p v-if="backtestJob?.request" class="hint">本次资金 {{ money(backtestJob.request.initialCapitalCny) }} · 预留现金 {{ backtestJob.request.cashPct ?? 0 }}% · {{ costsLabel(backtestJob.request.tradingCosts) }}</p>
            <p v-if="chartErrors.equity" class="error" role="alert">{{ chartErrors.equity }}</p>
            <div v-if="backtestResult" class="result-grid">
              <div><span>总收益率</span><b :class="tone(backtestMetrics?.totalReturnPct)">{{ formatPct(backtestMetrics?.totalReturnPct) }}</b></div>
              <div><span>年化收益率</span><b :class="tone(backtestMetrics?.annualizedReturnPct)">{{ formatPct(backtestMetrics?.annualizedReturnPct) }}</b></div>
              <div><span>最大回撤</span><b>{{ plainPct(backtestMetrics?.maxDrawdownPct) }}</b></div>
              <div><span>夏普</span><b>{{ formatNumber(backtestMetrics?.sharpe) }}</b></div>
              <div><span>Alpha</span><b :class="tone(backtestMetrics?.alphaPct)">{{ plainPct(backtestMetrics?.alphaPct) }}</b></div>
              <div><span>Beta</span><b>{{ formatNumber(backtestMetrics?.beta) }}</b></div>
            </div>
            <div v-show="backtestResult" ref="equityChart" class="chart"></div>
            <p v-if="!backtestResult" class="result-placeholder" :class="{ 'reserves-chart': backtestBusy }">
              {{ backtestBusy ? '等待回测任务完成…' : '配置参数并开始回测，或恢复历史任务以查看净值曲线。' }}
            </p>
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
              <div v-show="backtestResult?.accountCurve?.length" ref="exposureChart" class="chart exposure-chart"></div>
              <div v-if="lastAccount" class="hint">期末持仓 {{ plainPct(lastAccount.exposurePct) }} · 现金 {{ money(lastAccount.cashCny) }}；{{ lastAccount.positions.map(item => `${item.symbol} ${plainPct(item.weightPct)}`).join(' / ') || '无资产持仓' }}</div>
              <details class="trade-details"><summary>查看成交明细（{{ backtestResult?.trades?.length || 0 }} 笔）</summary><div class="table-card"><table><thead><tr><th>日期</th><th>资产</th><th>方向</th><th>成交价</th><th>数量</th><th>费用</th><th>滑点成本</th></tr></thead><tbody><tr v-for="(trade, index) in (backtestResult?.trades || [])" :key="index"><td>{{ trade.date }}</td><td>{{ trade.symbol }}</td><td>{{ trade.side === 'buy' ? '买入' : '卖出' }}</td><td>{{ formatNumber(trade.price) }}</td><td>{{ formatNumber(trade.quantity) }}</td><td>{{ money(trade.feeCny) }}</td><td>{{ money(trade.slippageCny) }}</td></tr><tr v-if="!backtestResult?.trades?.length"><td colspan="7">本次没有成交记录。</td></tr></tbody></table></div></details>
            </div>
          </article>
        </div>
      </section>

      <section id="ranking" class="panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-ranking" v-show="activeTab === 'ranking'">
        <header class="panel-head">
          <div>
            <h2>组合策略排行榜</h2>
            <p v-if="activeTab === 'ranking'" class="context-summary">{{ workspaceSummary }} · {{ workspaceResultState }}</p>
          </div>
          <span>资产可独立 · 其余配置跟随回测</span>
        </header>
        <div class="ranking-layout">
        <div class="ranking-main">
        <div class="ranking-config card">
          <div class="card-head"><h3>当前比较配置</h3><button type="button" class="link-btn" @click="selectTab('backtest')">调整回测配置 ↑</button></div>
          <div class="ranking-setup">
          <div class="form-section ranking-assets">
            <p class="group-kicker">研究标的</p>
            <AssetPicker v-model="rankingSymbols" :assets="assetCatalog" :loading="connection.loading" :error="assetCatalogError" label="排行资产" :disabled="rankingBusy" />
            <p v-if="rankingAssetsLinked" class="picker-follow hint">资产跟随回测；单独选择后仅影响排行。日期、资金、费用、基准及策略参数始终跟随回测。</p>
            <p v-else class="picker-follow hint">资产独立选择；日期、资金、费用、基准及策略参数跟随回测。<button type="button" class="link-btn ranking-follow-btn" :disabled="rankingBusy" @click="restoreRankingFollow">恢复跟随回测资产</button></p>
          </div>
          <dl class="ranking-facts ranking-draft">
            <div><dt>研究区间</dt><dd>{{ rankingState.draft.value.startDate && rankingState.draft.value.endDate ? `${rankingState.draft.value.startDate} 至 ${rankingState.draft.value.endDate}` : '待设置' }} · 前复权</dd></div>
            <div><dt>资金与现金</dt><dd>{{ money(rankingState.draft.value.initialCapitalCny) }} · 预留现金 {{ rankingState.draft.value.cashPct }}%</dd></div>
            <div class="span-2"><dt>费用口径</dt><dd>{{ costsLabel(rankingState.draft.value.tradingCosts) }}</dd></div>
            <div class="span-2"><dt>比较基准</dt><dd>{{ rankingBenchmarkLabel(rankingState.draft.value) }}</dd></div>
            <div class="span-2"><dt>当前策略参数</dt><dd>{{ backtest.selectedStrategy.value?.name || rankingState.draft.value.strategyId }} · {{ formatParameters(rankingState.draft.value.parameters) }}</dd></div>
          </dl>
          </div>
          <p class="config-note">所有入榜策略使用同一资产、日期、资金、费用与基准；其他候选使用各自默认参数，逐项展示；不适用策略列出原因。</p>
          <div class="flow-controls"><button class="primary" type="button" :disabled="!rankingState.canSubmit.value" @click="rankingState.submit">{{ rankingBusy ? '正在按配置计算…' : rankingMetadata ? '按当前配置刷新排行' : '按当前配置计算排行' }}</button><span>修改配置不会自动运行回测或重新计算排行。</span></div>
          <p v-if="rankingState.validationError.value" class="hint">{{ rankingState.validationError.value }}</p>
          <p v-if="rankingState.notice.value" class="notice" role="status">{{ rankingState.notice.value }}</p>
          <p v-if="rankingState.error.value" class="error" role="alert">{{ rankingState.error.value }}</p>
        </div>
        <p v-if="rankingState.stale.value" class="notice ranking-stale" role="status">已过期：排行配置、数据批次或模型目录已变化。下方保留上一次结果，请按当前配置刷新后再载入回测。</p>
        <div class="ranking-results-head">
          <h3>比较结果</h3>
          <span>{{ ranking.length ? `${ranking.length} 个策略入榜 · 按区间净收益排序` : rankingBusy ? '正在计算…' : '尚未计算' }}</span>
        </div>
        <article v-if="ranking.length" class="card table-card ranking-table" :class="{ 'ranking-outdated': rankingState.stale.value }" :aria-busy="rankingBusy" tabindex="0" aria-label="策略比较结果，可横向滚动">
          <table>
            <thead><tr><th scope="col" class="col-rank">排名</th><th scope="col">策略与参数</th><th scope="col">类型</th><th scope="col" class="num">区间收益</th><th scope="col" class="num">最大回撤</th><th scope="col" class="num">夏普</th><th scope="col" class="num">交易成本</th><th scope="col" class="col-action">联动研究</th></tr></thead>
            <tbody>
              <tr v-for="item in ranking" :key="item.strategyId">
                <td class="col-rank">{{ item.rank }}</td><td class="ranking-strategy"><strong>{{ item.strategyName }}</strong><small>参数 {{ formatParameters(item.parameters) }}</small><small v-if="item.benchmarkContext">基准：{{ item.benchmarkContext.label }}</small><small v-if="item.modelContext">模型 {{ item.modelContext.modelRef }}</small></td>
                <td class="ranking-category">{{ item.category === 'ai' ? 'AI · 实验' : '传统' }}</td>
                <td class="num" :class="tone(item.returnPct)">{{ formatPct(item.returnPct) }}</td>
                <td class="num">{{ plainPct(item.maxDrawdownPct) }}</td><td class="num">{{ formatNumber(item.sharpe) }}</td>
                <td class="num ranking-cost">{{ money(item.costSummary?.totalTradingCostCny) }}<small>{{ item.costSummary?.tradeCount ?? '未记录' }} 笔成交</small></td>
                <td class="col-action"><button class="secondary" type="button" :disabled="workflow.backtestLocked.value || rankingState.stale.value || rankingBusy" @click="loadRankedStrategy(item)">载入回测</button></td>
              </tr>
            </tbody>
          </table>
        </article>
        <p v-else class="result-placeholder" role="status">
          {{ rankingBusy ? '正在计算当前组合的可比结果…' : rankingMetadata ? '当前配置暂无可入榜策略，请查看排除原因或调整配置。' : '确认上方配置后，按当前配置计算排行。' }}
        </p>
        <p class="hint">按本区间净收益排序，历史表现不代表未来收益。策略训练范围、预热或执行口径不匹配时会排除，绝不换成其他资产或日期凑榜。</p>
        </div>
        <aside v-if="rankingMetadata || rankingUnavailable.length" class="ranking-side" aria-label="本次对比快照与排除说明">
          <div v-if="rankingMetadata" class="ranking-snapshot">
            <strong>本次结果快照{{ rankingState.stale.value ? '（历史配置）' : '' }}</strong>
            <dl class="ranking-facts compact">
              <div class="span-2"><dt>研究标的</dt><dd>{{ rankingMetadata.request.symbols.join('、') }}</dd></div>
              <div><dt>请求区间</dt><dd>{{ rankingMetadata.request.startDate }} 至 {{ rankingMetadata.request.endDate }}</dd></div>
              <div><dt>实际评价</dt><dd>{{ rankingMetadata.evaluationStartDate }} 至 {{ rankingMetadata.evaluationEndDate }} · {{ rankingMetadata.observationCount }} 个净值观察点</dd></div>
              <div class="span-2"><dt>资金与费用</dt><dd>{{ money(rankingMetadata.request.initialCapitalCny) }} · 预留现金 {{ rankingMetadata.request.cashPct }}% · {{ costsLabel(rankingMetadata.tradingCosts) }} · 前复权</dd></div>
              <div class="span-2"><dt>比较基准</dt><dd>{{ rankingBenchmarkLabel(rankingMetadata.request) }}</dd></div>
              <div v-if="rankingMetadata.dataContext" class="span-2"><dt>数据批次</dt><dd>{{ contextLabel(rankingMetadata.dataContext) }}</dd></div>
            </dl>
          </div>
          <details v-if="rankingUnavailable.length" class="ranking-exclusions" open><summary>未参与比较的策略（{{ rankingUnavailable.length }}）</summary><p v-for="item in rankingUnavailable" :key="item.strategyId" class="hint"><strong>{{ item.strategyName }}</strong>：{{ item.message }}</p></details>
        </aside>
        </div>
      </section>

      <section id="allocation" class="panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-allocation" v-show="activeTab === 'allocation'">
        <header class="panel-head">
          <div>
            <h2>下一交易日模拟配置</h2>
            <p v-if="activeTab === 'allocation'" class="context-summary">{{ workspaceSummary }} · {{ workspaceResultState }}</p>
          </div>
          <span>非实盘 · 不连接券商</span>
        </header>
        <div class="flow-controls"><button class="secondary" type="button" :disabled="allocationBusy" @click="workflow.restoreAllocation">恢复跟随回测</button><button class="secondary" type="button" :disabled="allocationBusy" @click="allocationConfigLinked = false">单独配置参数</button></div>
        <DataCapability :active="activeTab === 'allocation' && !connection.loading" :request="{ module: 'allocation', symbols: allocationSymbols, startDate: allocation.startDate.value || undefined }" :version="dataStatus.dataContext?.dataVersion" :assets="assetCatalog" :disabled="allocationBusy" @recover="recoverData('allocation', $event)" @checked="capabilityStates.allocation = $event" />
        <div class="allocation-setup">
          <div class="allocation-form">
            <article class="card form-card">
              <div class="form-section"><p class="group-kicker">研究标的</p><AssetPicker v-model="allocationSymbols" :assets="assetCatalog" :loading="connection.loading" :error="assetCatalogError" label="配置资产" :disabled="allocationBusy" />
              </div>
            </article>
            <article class="card form-card"><h3>策略与仓位</h3>
              <p class="hint">从 {{ allocation.startDate.value || '待设置' }} 重放至最新发布交易日，生成其下一交易日目标权重；回测结束日不作为“当前配置”的基准日。</p>
              <StrategyPicker v-model="allocationStrategyId" :strategies="allocation.availableStrategies.value" :disabled="allocationBusy"
                :empty-message="strategies.length ? '目录中暂无支持模拟配置的策略' : '策略目录尚未加载'" />
              <p v-if="allocationConfigLinked" class="hint">继承策略：{{ allocation.selectedStrategy.value?.name || allocationStrategyId }} · 参数 {{ formatParameters(allocation.parameters.value) }}；需修改共用配置请在回测区修改。</p>
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
            <p v-if="allocationError" class="error" role="alert">{{ allocationError }}{{ allocationResult ? '；本次未更新，已保留上一次成功结果。' : '' }}</p>
            <p v-else-if="allocation.validationError.value || capabilityStates.allocation === 'unavailable'" class="hint" role="status">{{ allocation.validationError.value || coverageWarning }}</p>
            <p class="disclaimer">仅用于教学研究，不构成投资建议，不会提交真实订单。</p>
          </article>
          </div>
          <article class="card" :aria-busy="allocationBusy">
            <p v-if="allocationBusy" class="notice" role="status">正在更新模拟配置…{{ allocationResult ? '下方保留上一次结果。' : '结果完成后将显示在这里。' }}</p>
            <div class="card-head"><h3>目标权重</h3><span>
              {{ allocationResult ? `${allocationResult.basisDate} → ${allocationResult.targetDate}` : '等待生成' }}
              <small v-if="allocationResult?.dataContext">{{ contextLabel(allocationResult.dataContext) }}</small>
            </span></div>
            <p v-if="allocation.resultStale.value" class="notice">草稿已变化，下方仍是上一次提交的模拟结果，请重新生成。</p>
            <p v-if="allocation.resultRequest.value" class="hint">本次配置：{{ allocation.resultRequest.value.strategyId }} · {{ allocation.resultRequest.value.symbols.join('、') }} · 起点 {{ allocation.resultRequest.value.startDate }} · 参数 {{ formatParameters(allocation.resultRequest.value.parameters) }} · {{ costsLabel(allocation.resultRequest.value.tradingCosts) }}</p>
            <p v-if="chartErrors.allocation" class="error" role="alert">{{ chartErrors.allocation }}</p>
            <div v-show="allocationResult" ref="allocationChart" class="chart small"></div>
            <p v-if="!allocationResult" class="result-placeholder" :class="{ 'reserves-chart': allocationBusy }">
              {{ allocationBusy ? '正在生成模拟权重…' : '确认资产、策略和现金比例后，生成模拟权重。' }}
            </p>
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
import { formatNumber, formatParameters, formatPct } from './dashboard/common'
import { WORKSPACE_TABS, useWorkspaceNavigation } from './dashboard/use-workspace-navigation.js'
import { createChartLifecycle } from './dashboard/chart-lifecycle.js'
import { useTheme } from './dashboard/use-theme'
import { useAllocation } from './dashboard/use-allocation'
import { useBacktest } from './dashboard/use-backtest'
import { useCorrelation } from './dashboard/use-correlation'
import { useMarket } from './dashboard/use-market'
import { useRanking } from './dashboard/use-ranking'
import { useResearchContext } from './dashboard/use-research-context'

const { connection, dataStatus, assetCatalog, market, strategies,
  historyStatusText, overviewStatusText, marketNotice, assetCatalogError, interfaceStatus, apiBaseUrl, initialise } = useMarket()
const correlation = useCorrelation(dataStatus)
const backtest = useBacktest(strategies, dataStatus, assetCatalog)
const allocation = useAllocation(strategies, undefined, dataStatus, assetCatalog)
const rankingState = useRanking(backtest, dataStatus, strategies)
const { result: rankingMetadata, items: ranking, unavailable: rankingUnavailable, busy: rankingBusy,
  symbols: rankingSymbols, assetsLinked: rankingAssetsLinked, restoreFollow: restoreRankingFollow } = rankingState
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
const coverageWarning = '数据覆盖不足，请查看本模块的数据检查。'

// CR077：昼夜主题；图表按当前主题初始化，切换时重建（init 主题无法在线切换）。
const { theme, toggleTheme } = useTheme()
const isLightTheme = computed(() => theme.value === 'light')

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
const chartErrors = ref({})
let mounted = false

const tabs = WORKSPACE_TABS
const navigation = useWorkspaceNavigation()
const { activeTab } = navigation
function selectTab(id) { navigation.select(id) }
async function focusPanel() {
  await nextTick()
  document.getElementById(activeTab.value)?.focus({ preventScroll: true })
}
function handleTabKey(event, index) {
  let next
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  selectTab(tabs[next].id)
  document.getElementById(`tab-${tabs[next].id}`)?.focus()
}
async function loadRankedStrategy(item) {
  if (!workflow.loadRanking(item, rankingMetadata.value)) return
  selectTab('backtest')
  await focusPanel()
}
const workspaceSummary = computed(() => {
  if (activeTab.value === 'correlation') return `${correlationSymbols.value.length} 只资产 · ${correlationStartDate.value || '日期待设置'} 至 ${correlationEndDate.value || '待设置'} · 独立研究`
  if (activeTab.value === 'allocation') return `${allocationSymbols.value.length} 只资产 · 起点 ${allocation.startDate.value || '待设置'} · ${allocationAssetsLinked.value ? '资产跟随回测' : '资产独立'} · ${allocationConfigLinked.value ? '参数跟随回测' : '参数独立'}`
  const ranking = activeTab.value === 'ranking'
  const request = ranking ? rankingState.draft.value : backtest.draft.value
  return `${request.symbols.length} 只资产 · ${request.startDate || '日期待设置'} 至 ${request.endDate || '待设置'} · ${ranking ? (rankingAssetsLinked.value ? '资产跟随回测' : '资产独立，其他配置跟随回测') : (backtestAssetsLinked.value ? '资产跟随相关性' : '资产独立')}`
})
const workspaceResultState = computed(() => {
  const current = { correlation, backtest, ranking: rankingState, allocation }[activeTab.value]
  if (!current) return ''
  if (current.busy.value) return '正在计算 / 更新'
  if (activeTab.value === 'backtest' && backtest.activeJob.value) return '任务未结束 · 可恢复查询'
  if (current.resultStale?.value || current.stale?.value) return '历史配置结果 · 需要更新'
  const result = activeTab.value === 'backtest' ? backtestResult.value : current.result?.value
  return result ? '已显示上次成功结果' : '尚无计算结果'
})
const jobStatusLabel = status => ({ queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }[status] || '状态待确认')

const formatInteger = (value) => value == null ? '—' : Number(value).toLocaleString('zh-CN')
const formatCny = (value) => value == null ? '—' : `${(Number(value) / 100000000).toFixed(2)} 亿元`
const plainPct = (value) => value == null ? '—' : `${Number(value).toFixed(2)}%`
const tone = (value) => value > 0 ? 'positive' : value < 0 ? 'negative' : ''
const actionLabel = (action) => ({ increase: '增加', hold: '持有', decrease: '降低', exit: '退出' }[action] || action)
const money = value => typeof value === 'number' && Number.isFinite(value) ? `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '未记录'
const rankingBenchmarkLabel = request => request.benchmarkMode === 'buy_and_hold' ? '所选组合初始等权买入持有基准（不计费用）' : request.benchmarkMode === 'custom' ? `自定义基准 ${request.benchmark}` : '无基准'
const costsLabel = costs => costs ? `佣金 ${costs.commissionPct}% / 滑点 ${costs.slippagePct}% / ${costs.stampDutyMode === 'asset_date' ? '印花税按资产及日期（ETF 免税）' : `固定卖出印花税 ${costs.stampDutyPct}%`}` : '费用口径未记录'

const lifecycle = createChartLifecycle({
  correlation: { tab: 'correlation', element: correlationChart, load: () => import('./lib/echarts-heatmap'), create: m => m.getHeatmapEcharts(), option: () => correlationOption(correlationResult.value, theme.value) },
  equity: { tab: 'backtest', element: equityChart, load: () => import('./lib/echarts-line'), create: m => m.getLineEcharts(), option: () => equityOption(backtestResult.value, theme.value) },
  exposure: { tab: 'backtest', element: exposureChart, load: () => import('./lib/echarts-line'), create: m => m.getLineEcharts(), option: () => exposureOption(backtestResult.value, theme.value) },
  allocation: { tab: 'allocation', element: allocationChart, load: () => import('./lib/echarts-pie'), create: m => m.getPieEcharts(), option: () => allocationOption(allocationResult.value, theme.value) }
}, { theme: () => theme.value, onError: (name, message) => { if (mounted) chartErrors.value[name] = message } })
let observer
const resizeCharts = async () => { await nextTick(); if (mounted) await lifecycle.sync(activeTab.value) }
onMounted(() => {
  mounted = true
  navigation.start()
  window.addEventListener('resize', resizeCharts)
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(resizeCharts)
    for (const el of [correlationChart, equityChart, exposureChart, allocationChart]) if (el.value) observer.observe(el.value)
  }
  void initialise()
  void resizeCharts()
})
watch([activeTab, theme], resizeCharts, { flush: 'post' })
watch(correlationResult, () => { lifecycle.update(['correlation']); void resizeCharts() }, { flush: 'post' })
watch(backtestResult, () => { lifecycle.update(['equity', 'exposure']); void resizeCharts() }, { flush: 'post' })
watch(allocationResult, () => { lifecycle.update(['allocation']); void resizeCharts() }, { flush: 'post' })
onBeforeUnmount(() => {
  mounted = false
  navigation.dispose()
  observer?.disconnect()
  window.removeEventListener('resize', resizeCharts)
  lifecycle.dispose()
})
</script>
