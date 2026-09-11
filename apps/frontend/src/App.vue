<template>
  <div class="dashboard">
    <header class="topbar">
      <a class="brand" href="#top" aria-label="智能量化分析平台首页">
        <span class="brand-mark">量</span>
        <span><strong>智能量化分析平台</strong><small>A 股与场内 ETF · 收盘后日更</small></span>
      </a>
      <nav>
        <a href="#market">市场概况</a>
        <a href="#correlation">资产相关性</a>
        <a href="#backtest">策略回测</a>
        <a href="#ranking">策略排行</a>
        <a href="#allocation">次日配置</a>
      </nav>
    </header>

    <main id="top" class="content">
      <section class="hero">
        <div>
          <p class="eyebrow">END-OF-DAY QUANT RESEARCH</p>
          <h1>用统一数据和可复现回测，完成每日市场复盘</h1>
          <p>
            当前可体验 2–10 个资产相关性、两种传统策略回测、策略排行及模拟配置。
            所有结果仅用于教学研究，不会提交真实订单。
          </p>
          <p class="notice">研究范围：{{ dataStatus.assetCount || assetCatalog.length }} 只资产，数据截至右侧所示日期。
            当前成分固定名单研究存在幸存者偏差；自动日更验收独立记录，AI策略尚未接入。</p>
          <div class="chips">
            <span>A 股 / ETF</span><span>AkShare</span><span>Flask + Pandas</span>
          </div>
        </div>
        <div class="status-card">
          <div class="status-line">
            <span :class="['status-dot', dataStatus.status]"></span>
            <strong>{{ connection.loading ? '连接中' : connection.message }}</strong>
          </div>
          <dl>
            <div><dt>最新交易日</dt><dd>{{ dataStatus.latestTradeDate || '等待数据' }}</dd></div>
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

      <section id="market" class="panel">
        <header class="panel-head">
          <div><p>MARKET OVERVIEW</p><h2>市场概况</h2></div>
          <span>{{ market.tradeDate ? `交易日 ${market.tradeDate}` : '等待收盘后日更' }}</span>
        </header>
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
        <div class="split">
          <article class="card form-card">
            <h3>选择 2–10 个资产</h3>
            <div v-for="(_, index) in correlationSymbols" :key="index" class="input-row">
              <input
                v-model.trim="correlationSymbols[index]"
                inputmode="numeric"
                maxlength="6"
                placeholder="六位代码，如 510300"
              />
              <button
                v-if="correlationSymbols.length > 2"
                class="secondary"
                type="button"
                @click="correlation.removeSymbol(index)"
              >删除</button>
            </div>
            <button
              v-if="correlationSymbols.length < 10"
              class="secondary full"
              type="button"
              @click="correlation.addSymbol"
            >添加资产</button>
            <div class="date-row">
              <label>开始日期<input v-model="correlationStartDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" /></label>
              <label>结束日期<input v-model="correlationEndDate" type="date" :min="correlation.minDate" :max="correlation.maxDate.value" /></label>
            </div>
            <button
              class="primary full"
              type="button"
              :disabled="!correlation.canSubmit.value || correlationBusy"
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
            <p v-if="correlationResult?.matrix.some(row => row.some(value => value == null))" class="hint">
              部分资产对无有效相关系数，留空显示；未以 0 代替。
            </p>
            <p v-if="chartErrors.correlation" class="error" role="alert">{{ chartErrors.correlation }}</p>
            <div ref="correlationChart" class="chart"></div>
          </article>
        </div>
      </section>

      <section id="backtest" class="panel">
        <header class="panel-head">
          <div><p>BACKTEST</p><h2>策略回测</h2></div>
          <span>收盘出信号 · 下一开盘成交</span>
        </header>
        <div class="split">
          <article class="card form-card">
            <label>资产（最多 10 个）
              <select v-model="backtestSymbols" multiple>
                <option v-for="asset in assetCatalog" :key="asset.symbol" :value="asset.symbol">
                  {{ asset.symbol }} · {{ asset.name }}
                </option>
              </select>
            </label>
            <label>策略
              <select v-model="backtestStrategyId">
                <option
                  v-for="strategy in strategies"
                  :key="strategy.id"
                  :value="strategy.id"
                  :disabled="strategy.status !== 'available'"
                >
                  {{ strategy.name }} · {{ strategyStatus(strategy.status) }}
                </option>
              </select>
            </label>
            <label v-for="field in backtest.parameterFields.value" :key="field.key">
              {{ field.label }}
              <input v-model.number="backtestParameters[field.key]" type="number"
                :name="field.key" :min="field.minimum" :max="field.maximum"
                :step="field.type === 'integer' ? 1 : 'any'" />
            </label>
            <label>比较基准
              <select v-model="backtestBenchmark">
                <option value="">无基准（Alpha / Beta 不适用）</option>
                <option v-for="asset in backtest.benchmarkOptions.value" :key="asset.symbol" :value="asset.symbol">
                  {{ asset.name }} · {{ asset.assetType === 'index' ? '价格指数' : 'ETF' }} · {{ asset.symbol }}
                </option>
              </select>
            </label>
            <p class="hint">ETF 为基金交易价格；指数仅在已校验快照可用时显示，使用价格指数收益，不冒充全收益指数。</p>
            <div class="date-row">
              <label>开始日期<input v-model="backtestStartDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" /></label>
              <label>结束日期<input v-model="backtestEndDate" type="date" :min="backtest.minDate" :max="backtest.maxDate.value" /></label>
            </div>
            <button
              class="primary full"
              type="button"
              :disabled="!backtest.canSubmit.value"
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
          </article>
          <article class="card">
            <div class="card-head"><h3>{{ backtest.strategyName.value }}结果</h3><span>
              {{ backtestResult ? '真实回测输出' : '尚未运行' }}
            </span></div>
            <p v-if="backtestJob" class="hint">{{ backtest.benchmarkLabel.value }}</p>
            <p v-if="backtestJob?.request" class="hint">
              {{ backtestJob.request.startDate }} 至 {{ backtestJob.request.endDate }} ·
              {{ backtestJob.request.symbols.join('、') }} · 参数 {{ JSON.stringify(backtestJob.request.parameters) }}
            </p>
            <p v-if="chartErrors.equity" class="error" role="alert">{{ chartErrors.equity }}</p>
            <div ref="equityChart" class="chart"></div>
            <div class="result-grid">
              <div><span>总收益率</span><b>{{ formatPct(backtestMetrics?.totalReturnPct) }}</b></div>
              <div><span>年化收益率</span><b>{{ formatPct(backtestMetrics?.annualizedReturnPct) }}</b></div>
              <div><span>最大回撤</span><b>{{ plainPct(backtestMetrics?.maxDrawdownPct) }}</b></div>
              <div><span>夏普</span><b>{{ formatNumber(backtestMetrics?.sharpe) }}</b></div>
              <div><span>Alpha</span><b>{{ plainPct(backtestMetrics?.alphaPct) }}</b></div>
              <div><span>Beta</span><b>{{ formatNumber(backtestMetrics?.beta) }}</b></div>
            </div>
          </article>
        </div>
      </section>

      <section id="ranking" class="panel">
        <p v-if="rankingContext" class="hint">{{ contextLabel(rankingContext) }} · 510300ETF代表资产 · 默认参数及费用</p>
        <header class="panel-head">
          <div><p>STRATEGY RANKING</p><h2>策略排行榜</h2></div>
          <span>近 30 个自然日 · 收盘后更新</span>
        </header>
        <article class="card table-card">
          <table>
            <thead><tr><th>排名</th><th>策略</th><th>类型</th><th>区间收益</th><th>最大回撤</th><th>夏普</th></tr></thead>
            <tbody>
              <tr v-for="item in ranking" :key="item.strategyId">
                <td>{{ item.rank }}</td><td>{{ item.strategyName }}</td><td>{{ item.category === 'ai' ? 'AI' : '传统' }}</td>
                <td :class="tone(item.returnPct)">{{ formatPct(item.returnPct) }}</td>
                <td>{{ plainPct(item.maxDrawdownPct) }}</td><td>{{ formatNumber(item.sharpe) }}</td>
              </tr>
              <tr v-if="!ranking.length"><td colspan="6" class="empty">暂无真实排行；算法完成并日更后自动显示。</td></tr>
            </tbody>
          </table>
        </article>
      </section>

      <section id="allocation" class="panel">
        <header class="panel-head">
          <div><p>NEXT-DAY ALLOCATION</p><h2>下一交易日模拟配置</h2></div>
          <span>非实盘 · 不连接券商</span>
        </header>
        <div class="split">
          <article class="card form-card">
            <label>资产池
              <select v-model="allocationSymbols" multiple>
                <option v-for="asset in assetCatalog" :key="asset.symbol" :value="asset.symbol">
                  {{ asset.symbol }} · {{ asset.name }}
                </option>
              </select>
            </label>
            <label>策略
              <select v-model="allocationStrategyId">
                <option v-for="strategy in allocation.availableStrategies.value" :key="strategy.id" :value="strategy.id">
                  {{ strategy.name }}
                </option>
              </select>
            </label>
            <label>现金比例（%）<input v-model.number="allocationCashPct" type="number" min="0" max="100" /></label>
            <button
              class="primary full"
              type="button"
              :disabled="!allocation.canSubmit.value"
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
            <p v-if="chartErrors.allocation" class="error" role="alert">{{ chartErrors.allocation }}</p>
            <div ref="allocationChart" class="chart small"></div>
            <div v-if="allocationResult" class="position-list">
              <div>
                <strong>现金</strong><span>{{ allocationResult.cashPct }}%</span>
                <small>实际现金权重（含策略退出后保留的现金）</small>
              </div>
              <div v-for="position in allocationResult.positions" :key="position.symbol">
                <strong>{{ position.symbol }}</strong><span>{{ position.weightPct }}%</span>
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
const contextLabel = context => `发布截止 ${context.publicationDate} · 数据 ${context.dataVersion.slice(0, 12)} · 名单 ${context.universeVersion.slice(0, 12)}（${context.consistency === 'published_snapshot' ? '完整不可变发布' : '旧池修订'}）`

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { allocationOption, correlationOption, equityOption } from './dashboard/charts'
import { formatNumber, formatPct } from './dashboard/common'
import { useAllocation } from './dashboard/use-allocation'
import { useBacktest } from './dashboard/use-backtest'
import { useCorrelation } from './dashboard/use-correlation'
import { useMarket } from './dashboard/use-market'
import { initialiseDashboard } from './dashboard/startup'

const { connection, dataStatus, assetCatalog, market, strategies, ranking, rankingContext,
  historyStatusText, overviewStatusText, marketNotice, assetCatalogError, initialise } = useMarket()
const correlation = useCorrelation(dataStatus)
const backtest = useBacktest(strategies, dataStatus, assetCatalog)
const allocation = useAllocation(strategies)

const { symbols: correlationSymbols, startDate: correlationStartDate, endDate: correlationEndDate,
  result: correlationResult, busy: correlationBusy, error: correlationError,
  validSymbols: correlationValidSymbols } = correlation
const { symbols: backtestSymbols, strategyId: backtestStrategyId, startDate: backtestStartDate,
  endDate: backtestEndDate, job: backtestJob, busy: backtestBusy, error: backtestError,
  parameters: backtestParameters, benchmark: backtestBenchmark, recoveryId: backtestRecoveryId } = backtest
const { symbols: allocationSymbols, strategyId: allocationStrategyId, cashPct: allocationCashPct,
  result: allocationResult, busy: allocationBusy, error: allocationError } = allocation

const backtestResult = computed(() => backtestJob.value?.result || null)
const backtestMetrics = computed(() => backtestResult.value?.metrics || null)
const correlationChart = ref(null)
const equityChart = ref(null)
const allocationChart = ref(null)
const charts = {}
const chartErrors = ref({})
let mounted = false

const formatInteger = (value) => value == null ? '—' : Number(value).toLocaleString('zh-CN')
const formatCny = (value) => value == null ? '—' : `${(Number(value) / 100000000).toFixed(2)} 亿元`
const plainPct = (value) => value == null ? '—' : `${Number(value).toFixed(2)}%`
const tone = (value) => value > 0 ? 'positive' : value < 0 ? 'negative' : ''
const strategyStatus = (status) => ({ available: '可用', experimental: '试验中', planned: '规划中' }[status] || status)
const actionLabel = (action) => ({ increase: '增加', hold: '持有', decrease: '降低', exit: '退出' }[action] || action)

const resizeCharts = () => Object.values(charts).forEach((chart) => chart?.resize())

onMounted(async () => {
  mounted = true
  await nextTick()
  if (!mounted) return
  const startChart = async (name, load, create, element, option) => {
    const module = await load()
    if (!mounted) return
    charts[name] = create(module).init(element.value)
    charts[name].setOption(option())
  }
  window.addEventListener('resize', resizeCharts)
  await initialiseDashboard(initialise, {
    correlation: () => startChart('correlation', () => import('./lib/echarts-heatmap'),
      module => module.getHeatmapEcharts(), correlationChart, () => correlationOption(correlationResult.value)),
    equity: () => startChart('equity', () => import('./lib/echarts-line'),
      module => module.getLineEcharts(), equityChart, () => equityOption(backtestResult.value)),
    allocation: () => startChart('allocation', () => import('./lib/echarts-pie'),
      module => module.getPieEcharts(), allocationChart, () => allocationOption(allocationResult.value))
  }, name => {
    if (mounted) chartErrors.value[name] = '图表加载失败，请刷新页面重试；已取得的数据和计算结果仍可查看。'
  })
})

watch(correlationResult, (value) => charts.correlation?.setOption(correlationOption(value), true))
watch(backtestResult, (value) => charts.equity?.setOption(equityOption(value), true))
watch(allocationResult, (value) => charts.allocation?.setOption(allocationOption(value), true))

onBeforeUnmount(() => {
  mounted = false
  window.removeEventListener('resize', resizeCharts)
  Object.values(charts).forEach((chart) => chart?.dispose())
})
</script>

<style scoped src="./styles/dashboard.css"></style>
