<template>
  <div class="dashboard">
    <header class="topbar">
      <div class="brand">
        <span class="brand-dot"></span>
        <div>
          <p class="brand-title">智能量化分析平台</p>
          <p class="brand-subtitle">AI Quant Dashboard</p>
        </div>
      </div>
      <nav class="topnav">
        <a href="#market-overview">市场概况</a>
        <a href="#correlation-analysis">相关性分析</a>
        <a href="#strategy-backtest">策略回测</a>
        <a href="#algorithm-ranking">策略排行</a>
        <a href="#real-time-suggestion">实时建议</a>
      </nav>
    </header>

    <main class="content">
      <section class="hero">
        <div class="hero-copy">
          <p class="hero-tag">实时洞察</p>
          <h1>一屏查看市场热度、策略表现与资产配置建议</h1>
          <p class="hero-desc">
            统一接入行情、回测与策略评分模块，帮助你更快完成日内复盘与次日调仓决策。
          </p>
          <div class="hero-actions" aria-label="平台模块">
            <span>行情监控</span>
            <span>相关性分析</span>
            <span>回测验证</span>
          </div>
        </div>
        <div class="hero-stats">
          <div class="hero-stat">
            <p>今日策略胜率</p>
            <strong>74.6%</strong>
            <span class="stat-bar"><i style="width: 74.6%"></i></span>
          </div>
          <div class="hero-stat">
            <p>监控资产数</p>
            <strong>128</strong>
            <span class="stat-bar"><i style="width: 82%"></i></span>
          </div>
          <div class="hero-stat">
            <p>风险预警</p>
            <strong class="text-warning">3 条</strong>
            <span class="stat-bar warning"><i style="width: 36%"></i></span>
          </div>
        </div>
      </section>

      <section id="market-overview" class="panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Market Overview</p>
            <h2>市场概况</h2>
          </div>
          <span class="panel-meta">盘中快照 · 15:00</span>
        </div>
        <div class="market-grid">
          <article class="card">
            <h3>市场情绪</h3>
            <div class="sentiment-meter" aria-label="市场情绪中性偏强">
              <span style="width: 58%"></span>
            </div>
            <div class="kv"><span>上涨家数</span><b class="text-positive">2,156</b></div>
            <div class="kv"><span>下跌家数</span><b class="text-negative">1,844</b></div>
            <div class="kv"><span>情绪温度</span><b class="text-warning">中性偏强</b></div>
          </article>
          <article class="card">
            <h3>主流指数</h3>
            <div v-for="item in indexPerformance" :key="item.name" class="kv">
              <span>{{ item.name }} {{ item.value }}</span>
              <b :class="item.change >= 0 ? 'text-positive' : 'text-negative'">
                {{ item.change >= 0 ? '+' : '' }}{{ item.change }}%
              </b>
            </div>
          </article>
          <article class="card chart-card">
            <div class="card-title-row">
              <h3>资金热度</h3>
              <span>行业净流向</span>
            </div>
            <div ref="fundHeatChart" class="chart"></div>
          </article>
        </div>
      </section>

      <section id="correlation-analysis" class="panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Correlation</p>
            <h2>资产相关性分析</h2>
          </div>
          <span class="panel-meta">{{ validAssets.length }} 个有效资产</span>
        </div>
        <div class="two-col">
          <article class="card">
            <h3>资产池配置（最多 10 个）</h3>
            <div class="asset-list">
              <div v-for="(asset, index) in assets" :key="index" class="input-row">
                <input v-model="assets[index]" type="text" placeholder="输入资产代码，如 AAPL" maxlength="10" />
                <button v-if="assets.length > 1" type="button" class="ghost-btn" @click="removeAsset(index)">
                  删除
                </button>
              </div>
              <button v-if="assets.length < 10" type="button" class="primary-btn" @click="addAsset">
                添加资产
              </button>
            </div>
            <p class="form-note" :class="{ 'text-warning': validAssets.length < 2 }">
              {{ validAssets.length >= 2 ? '热力图将根据当前资产池自动刷新。' : '至少保留 2 个有效资产用于相关性分析。' }}
            </p>
          </article>
          <article class="card chart-card">
            <div class="card-title-row">
              <h3>相关性热力图</h3>
              <span>0 弱相关 · 1 强相关</span>
            </div>
            <div ref="correlationChart" class="chart tall"></div>
          </article>
        </div>
      </section>

      <section id="strategy-backtest" class="panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Backtest</p>
            <h2>策略回测引擎</h2>
          </div>
          <span class="panel-meta">{{ selectedAssets.length }} 个资产 · {{ strategyLabel }}</span>
        </div>
        <div class="two-col">
          <article class="card">
            <h3>参数设置</h3>
            <div class="form-group">
              <label>选择资产</label>
              <select v-model="selectedAssets" multiple>
                <option v-for="asset in availableAssets" :key="asset" :value="asset">{{ asset }}</option>
              </select>
              <p class="form-note">按住 Ctrl / Command 可多选。</p>
            </div>
            <div class="form-group">
              <label>选择策略</label>
              <select v-model="selectedStrategy">
                <option value="ma_crossover">均线交叉</option>
                <option value="momentum_reversal">动量反转</option>
                <option value="reinforcement_learning">强化学习</option>
                <option value="multi_agent">多智能体</option>
              </select>
            </div>
            <div class="date-grid">
              <div class="form-group">
                <label>开始时间</label>
                <input v-model="startDate" type="date" />
              </div>
              <div class="form-group">
                <label>结束时间</label>
                <input v-model="endDate" type="date" />
              </div>
            </div>
            <button class="primary-btn full-btn" type="button" :disabled="!canRunBacktest" @click="runBacktest">
              运行回测
            </button>
          </article>
          <article class="card">
            <div class="card-title-row">
              <h3>回测结果</h3>
              <span>{{ backtestSummary }}</span>
            </div>
            <div class="chart-grid">
              <div>
                <p class="chart-label">累计收益</p>
                <div ref="returnChart" class="chart compact"></div>
              </div>
              <div>
                <p class="chart-label">最大回撤</p>
                <div ref="drawdownChart" class="chart compact"></div>
              </div>
            </div>
            <div class="metrics-grid">
              <div class="metric">
                <p>夏普比率</p>
                <strong>{{ backtestMetrics.sharpeRatio }}</strong>
              </div>
              <div class="metric">
                <p>Alpha</p>
                <strong>{{ backtestMetrics.alpha }}</strong>
              </div>
              <div class="metric">
                <p>Beta</p>
                <strong>{{ backtestMetrics.beta }}</strong>
              </div>
              <div class="metric">
                <p>最大回撤</p>
                <strong class="text-negative">{{ backtestMetrics.maxDrawdown }}</strong>
              </div>
              <div class="metric">
                <p>总收益率</p>
                <strong class="text-positive">{{ backtestMetrics.totalReturn }}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section id="algorithm-ranking" class="panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Ranking</p>
            <h2>策略排行榜</h2>
          </div>
          <span class="panel-meta">按综合表现排序</span>
        </div>
        <div class="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>排名</th>
                <th>策略名</th>
                <th>今日</th>
                <th>近 7 日</th>
                <th>近 30 日</th>
                <th>年化收益</th>
                <th>夏普</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(strategy, index) in strategyRanking" :key="strategy.name">
                <td>{{ index + 1 }}</td>
                <td>{{ strategy.name }}</td>
                <td :class="strategy.todayReturn >= 0 ? 'text-positive' : 'text-negative'">
                  {{ strategy.todayReturn >= 0 ? '+' : '' }}{{ strategy.todayReturn }}%
                </td>
                <td :class="strategy.weekReturn >= 0 ? 'text-positive' : 'text-negative'">
                  {{ strategy.weekReturn >= 0 ? '+' : '' }}{{ strategy.weekReturn }}%
                </td>
                <td :class="strategy.monthReturn >= 0 ? 'text-positive' : 'text-negative'">
                  {{ strategy.monthReturn >= 0 ? '+' : '' }}{{ strategy.monthReturn }}%
                </td>
                <td :class="strategy.annualReturn >= 0 ? 'text-positive' : 'text-negative'">
                  {{ strategy.annualReturn >= 0 ? '+' : '' }}{{ strategy.annualReturn }}%
                </td>
                <td>{{ strategy.sharpeRatio }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section id="real-time-suggestion" class="panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Allocation</p>
            <h2>实时配置建议</h2>
          </div>
          <span class="panel-meta">{{ selectedAssetPool.length || 4 }} 个资产生成</span>
        </div>
        <div class="two-col">
          <article class="card">
            <h3>可选资产池</h3>
            <div class="check-list">
              <label v-for="asset in availableAssets" :key="asset">
                <input v-model="selectedAssetPool" type="checkbox" :value="asset" />
                <span>{{ asset }}</span>
              </label>
            </div>
            <button class="primary-btn full-btn" type="button" @click="generateSuggestion">生成建议</button>
            <p class="form-note">未勾选时默认使用前 4 个资产生成配置。</p>
          </article>
          <article class="card">
            <div class="card-title-row">
              <h3>次日配置权重</h3>
              <span>合计 {{ totalSuggestionWeight }}%</span>
            </div>
            <div ref="weightChart" class="chart"></div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>资产</th>
                    <th>建议权重</th>
                    <th>昨日表现</th>
                    <th>趋势判断</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in suggestionResults" :key="item.asset">
                    <td>{{ item.asset }}</td>
                    <td>{{ item.weight }}%</td>
                    <td :class="item.yesterdayPerformance >= 0 ? 'text-positive' : 'text-negative'">
                      {{ item.yesterdayPerformance >= 0 ? '+' : '' }}{{ item.yesterdayPerformance }}%
                    </td>
                    <td :class="item.trend === '上涨' ? 'text-positive' : item.trend === '下跌' ? 'text-negative' : 'text-warning'">
                      {{ item.trend }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </div>
      </section>
    </main>

    <footer class="footer">
      <p>© 2026 智能量化分析平台 · Frontend Preview</p>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const fundHeatChart = ref(null)
const correlationChart = ref(null)
const returnChart = ref(null)
const drawdownChart = ref(null)
const weightChart = ref(null)

const assets = ref(['AAPL', 'MSFT', 'GOOGL', 'AMZN'])
const availableAssets = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'JNJ']
const selectedAssets = ref(['AAPL', 'MSFT'])
const selectedStrategy = ref('ma_crossover')
const startDate = ref('2025-01-01')
const endDate = ref('2025-12-31')

const strategyNames = {
  ma_crossover: '均线交叉',
  momentum_reversal: '动量反转',
  reinforcement_learning: '强化学习',
  multi_agent: '多智能体'
}

const indexPerformance = [
  { name: '上证指数', value: '3,258.63', change: 0.85 },
  { name: '深证成指', value: '10,897.32', change: 1.23 },
  { name: '创业板指', value: '2,176.45', change: -0.32 },
  { name: '沪深 300', value: '4,125.78', change: 0.97 }
]

const strategyRanking = ref([
  { name: '强化学习策略', todayReturn: 2.5, weekReturn: 8.2, monthReturn: 15.6, annualReturn: 32.4, sharpeRatio: 1.8 },
  { name: '均线交叉策略', todayReturn: 1.8, weekReturn: 6.5, monthReturn: 12.3, annualReturn: 28.7, sharpeRatio: 1.5 },
  { name: '动量反转策略', todayReturn: 1.2, weekReturn: 5.8, monthReturn: 10.9, annualReturn: 25.3, sharpeRatio: 1.3 },
  { name: '多智能体策略', todayReturn: 0.8, weekReturn: 4.2, monthReturn: 9.1, annualReturn: 22.6, sharpeRatio: 1.2 }
])

const selectedAssetPool = ref(['AAPL', 'MSFT', 'GOOGL', 'AMZN'])
const suggestionResults = ref([
  { asset: 'AAPL', weight: 30, yesterdayPerformance: 1.2, trend: '上涨' },
  { asset: 'MSFT', weight: 25, yesterdayPerformance: 0.8, trend: '上涨' },
  { asset: 'GOOGL', weight: 20, yesterdayPerformance: -0.3, trend: '中性' },
  { asset: 'AMZN', weight: 25, yesterdayPerformance: 1.5, trend: '上涨' }
])

const backtestMetrics = reactive({
  sharpeRatio: '1.25',
  alpha: '0.08',
  beta: '0.92',
  maxDrawdown: '-12.5%',
  totalReturn: '24.8%'
})

const returnSeries = ref([0, 2.5, 5.8, 3.2, 8.5, 12.3, 10.1, 15.6, 18.2, 20.5, 22.8, 24.8])
const drawdownSeries = ref([0, -2.1, -5.3, -3.2, -7.5, -10.2, -8.1, -12.5, -9.8, -6.5, -4.2, -3.1])

const validAssets = computed(() => {
  const normalized = assets.value
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
  return [...new Set(normalized)].slice(0, 10)
})

const strategyLabel = computed(() => strategyNames[selectedStrategy.value] || '未选择策略')
const canRunBacktest = computed(() => selectedAssets.value.length > 0 && startDate.value && endDate.value && startDate.value <= endDate.value)
const backtestSummary = computed(() => `${strategyLabel.value} · ${startDate.value} 至 ${endDate.value}`)
const totalSuggestionWeight = computed(() => {
  const total = suggestionResults.value.reduce((sum, item) => sum + Number(item.weight), 0)
  return Number(total.toFixed(1))
})

const chartMap = {}
let chartObserver = null
let heatmapEcharts = null
let lineEcharts = null
let pieEcharts = null

const loadHeatmapEcharts = async () => {
  if (heatmapEcharts) {
    return heatmapEcharts
  }
  const mod = await import('./lib/echarts-heatmap')
  heatmapEcharts = mod.getHeatmapEcharts()
  return heatmapEcharts
}

const loadLineEcharts = async () => {
  if (lineEcharts) {
    return lineEcharts
  }
  const mod = await import('./lib/echarts-line')
  lineEcharts = mod.getLineEcharts()
  return lineEcharts
}

const loadPieEcharts = async () => {
  if (pieEcharts) {
    return pieEcharts
  }
  const mod = await import('./lib/echarts-pie')
  pieEcharts = mod.getPieEcharts()
  return pieEcharts
}

const palette = {
  axis: '#5f6b86',
  grid: '#e8edf7',
  blue: '#1d6fff',
  cyan: '#17c5cf',
  red: '#ef5350',
  orange: '#ff8f00'
}

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

const getSeed = (parts) => {
  const source = parts.join('|')
  let seed = 0
  for (let i = 0; i < source.length; i += 1) {
    seed = (seed * 31 + source.charCodeAt(i)) % 9973
  }
  return seed
}

const seededValue = (seed, index, min, max) => {
  const raw = Math.sin(seed + index * 12.9898) * 43758.5453
  const fraction = raw - Math.floor(raw)
  return min + fraction * (max - min)
}

const addAsset = () => {
  if (assets.value.length < 10) {
    assets.value.push('')
  }
}

const removeAsset = (index) => {
  if (assets.value.length > 1) {
    assets.value.splice(index, 1)
  }
}

const runBacktest = () => {
  if (!canRunBacktest.value) {
    return
  }

  const seed = getSeed([selectedStrategy.value, selectedAssets.value.join(','), startDate.value, endDate.value])
  const strategyBoost = {
    ma_crossover: 0.95,
    momentum_reversal: 0.88,
    reinforcement_learning: 1.16,
    multi_agent: 1.05
  }[selectedStrategy.value] || 1
  const diversification = clamp(selectedAssets.value.length / 6, 0.2, 1.4)
  const monthly = []
  let cumulative = 0
  let peak = 0
  const drawdowns = []

  for (let i = 0; i < 12; i += 1) {
    const drift = seededValue(seed, i, -1.4, 4.2) * strategyBoost
    cumulative = Number((cumulative + drift + diversification * 0.45).toFixed(1))
    peak = Math.max(peak, cumulative)
    monthly.push(cumulative)
    drawdowns.push(Number(Math.min(0, cumulative - peak - seededValue(seed, i + 20, 0, 2.8)).toFixed(1)))
  }

  returnSeries.value = monthly
  drawdownSeries.value = drawdowns

  const totalReturn = monthly.at(-1)
  const maxDrawdown = Math.min(...drawdowns)
  backtestMetrics.sharpeRatio = (1.05 + (Math.max(totalReturn, 0) / 38) + diversification * 0.12).toFixed(2)
  backtestMetrics.alpha = (0.04 + Math.max(totalReturn, 0) / 360).toFixed(2)
  backtestMetrics.beta = (0.82 + selectedAssets.value.length * 0.025).toFixed(2)
  backtestMetrics.maxDrawdown = `${maxDrawdown.toFixed(1)}%`
  backtestMetrics.totalReturn = `${totalReturn.toFixed(1)}%`

  chartMap.return?.setOption(createReturnOption(), true)
  chartMap.drawdown?.setOption(createDrawdownOption(), true)
}

const generateSuggestion = () => {
  const pool = selectedAssetPool.value.length > 0 ? selectedAssetPool.value : availableAssets.slice(0, 4)
  const raw = pool.map((asset) => ({
    asset,
    score: 10 + Math.random() * 40,
    yesterdayPerformance: Number((Math.random() * 4 - 1.5).toFixed(2))
  }))
  const total = raw.reduce((sum, item) => sum + item.score, 0)
  const normalized = raw.map((item) => {
    const weight = Number(((item.score / total) * 100).toFixed(1))
    return {
      asset: item.asset,
      weight,
      yesterdayPerformance: item.yesterdayPerformance,
      trend: item.yesterdayPerformance > 0.5 ? '上涨' : item.yesterdayPerformance < -0.5 ? '下跌' : '中性'
    }
  })

  const diff = Number((100 - normalized.reduce((sum, item) => sum + item.weight, 0)).toFixed(1))
  if (normalized.length > 0) {
    normalized[0].weight = Number((normalized[0].weight + diff).toFixed(1))
  }
  suggestionResults.value = normalized
  updateWeightChart()
}

const createFundHeatOption = () => ({
  tooltip: { position: 'top' },
  grid: { left: 10, right: 10, top: 20, bottom: 40, containLabel: true },
  xAxis: {
    type: 'category',
    data: ['科技', '金融', '消费', '医药', '能源'],
    axisLine: { lineStyle: { color: palette.grid } },
    axisLabel: { color: palette.axis }
  },
  yAxis: {
    type: 'category',
    data: ['净流入', '净流出'],
    axisLine: { lineStyle: { color: palette.grid } },
    axisLabel: { color: palette.axis }
  },
  visualMap: {
    min: -100,
    max: 100,
    orient: 'horizontal',
    left: 'center',
    bottom: 0,
    inRange: { color: ['#ffe3e0', '#f8f9ff', '#e2f4ff'] }
  },
  series: [{
    name: '资金热度',
    type: 'heatmap',
    data: [[0, 0, 78], [1, 0, 40], [2, 0, 60], [3, 0, 70], [4, 0, 28], [0, 1, -26], [1, 1, -18], [2, 1, -32], [3, 1, -15], [4, 1, -44]],
    label: { show: true, formatter: '{c}', color: '#2f3954' }
  }]
})

const createCorrelationOption = () => {
  const labels = validAssets.value.length >= 2 ? validAssets.value : ['AAPL', 'MSFT']
  const points = []
  for (let i = 0; i < labels.length; i += 1) {
    for (let j = 0; j < labels.length; j += 1) {
      const distance = Math.abs(i - j)
      const base = i === j ? 1 : Number(clamp(0.92 - distance * 0.12 + seededValue(getSeed(labels), i + j, -0.08, 0.08), 0.25, 0.92).toFixed(2))
      points.push([i, j, base])
    }
  }
  return {
    tooltip: { position: 'top' },
    grid: { left: 10, right: 10, top: 20, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: labels, axisLabel: { color: palette.axis } },
    yAxis: { type: 'category', data: labels, axisLabel: { color: palette.axis } },
    visualMap: {
      min: 0,
      max: 1,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#fff4d4', '#dceeff', '#5c7cff'] }
    },
    series: [{ type: 'heatmap', data: points, label: { show: true, formatter: '{c}' } }]
  }
}

const createReturnOption = () => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 45, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'], axisLabel: { color: palette.axis } },
  yAxis: { type: 'value', axisLabel: { color: palette.axis } },
  series: [{
    data: returnSeries.value,
    type: 'line',
    smooth: true,
    symbol: 'none',
    lineStyle: { color: palette.blue, width: 3 },
    areaStyle: { color: 'rgba(29,111,255,0.15)' }
  }]
})

const createDrawdownOption = () => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 45, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'], axisLabel: { color: palette.axis } },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: palette.axis } },
  series: [{
    data: drawdownSeries.value,
    type: 'line',
    smooth: true,
    symbol: 'none',
    lineStyle: { color: palette.red, width: 3 },
    areaStyle: { color: 'rgba(239,83,80,0.14)' }
  }]
})

const createWeightOption = () => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
  legend: { top: 0, textStyle: { color: palette.axis } },
  series: [{
    type: 'pie',
    radius: ['42%', '70%'],
    top: 24,
    data: suggestionResults.value.map((item) => ({ name: item.asset, value: item.weight })),
    label: { formatter: '{b}\\n{d}%' },
    itemStyle: {
      borderRadius: 8,
      borderColor: '#fff',
      borderWidth: 2
    },
    color: ['#1d6fff', '#17c5cf', '#ff8f00', '#ef5350', '#36b37e', '#6d5efc']
  }]
})

const initFundChart = async () => {
  if (chartMap.fund || !fundHeatChart.value) {
    return
  }
  const echarts = await loadHeatmapEcharts()
  chartMap.fund = echarts.init(fundHeatChart.value)
  chartMap.fund.setOption(createFundHeatOption())
}

const initCorrelationChart = async () => {
  if (chartMap.correlation || !correlationChart.value) {
    return
  }
  const echarts = await loadHeatmapEcharts()
  chartMap.correlation = echarts.init(correlationChart.value)
  chartMap.correlation.setOption(createCorrelationOption())
}

const initReturnChart = async () => {
  if (chartMap.return || !returnChart.value) {
    return
  }
  const echarts = await loadLineEcharts()
  chartMap.return = echarts.init(returnChart.value)
  chartMap.return.setOption(createReturnOption())
}

const initDrawdownChart = async () => {
  if (chartMap.drawdown || !drawdownChart.value) {
    return
  }
  const echarts = await loadLineEcharts()
  chartMap.drawdown = echarts.init(drawdownChart.value)
  chartMap.drawdown.setOption(createDrawdownOption())
}

const initWeightChart = async () => {
  if (chartMap.weight || !weightChart.value) {
    return
  }
  const echarts = await loadPieEcharts()
  chartMap.weight = echarts.init(weightChart.value)
  chartMap.weight.setOption(createWeightOption())
}

const observeChart = (element, initFn) => {
  if (!element || !chartObserver) {
    return
  }
  element.__chartInitFn = initFn
  chartObserver.observe(element)
}

const setupChartObserver = () => {
  chartObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting && entry.target.__chartInitFn) {
        entry.target.__chartInitFn()
        chartObserver.unobserve(entry.target)
      }
    })
  }, {
    root: null,
    threshold: 0.1,
    rootMargin: '120px 0px'
  })

  observeChart(fundHeatChart.value, initFundChart)
  observeChart(correlationChart.value, initCorrelationChart)
  observeChart(returnChart.value, initReturnChart)
  observeChart(drawdownChart.value, initDrawdownChart)
  observeChart(weightChart.value, initWeightChart)
}

const handleResize = () => {
  Object.values(chartMap).forEach((chart) => chart?.resize())
}

const updateCorrelationChart = () => {
  chartMap.correlation?.setOption(createCorrelationOption(), true)
}

const updateWeightChart = () => {
  chartMap.weight?.setOption(createWeightOption(), true)
}

watch(assets, () => {
  updateCorrelationChart()
}, { deep: true })

onMounted(async () => {
  await nextTick()
  setupChartObserver()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartObserver) {
    chartObserver.disconnect()
  }
  Object.values(chartMap).forEach((chart) => chart?.dispose())
})
</script>

<style scoped>
.dashboard {
  --ink: #111827;
  --muted: #64748b;
  --soft: #f8fafc;
  --surface: rgba(255, 255, 255, 0.9);
  --surface-strong: rgba(255, 255, 255, 0.98);
  --line: rgba(15, 23, 42, 0.09);
  --line-strong: rgba(37, 99, 235, 0.18);
  --blue: #2563eb;
  --cyan: #0891b2;
  --green: #16a34a;
  --amber: #f59e0b;
  --red: #e11d48;
  --shadow-sm: 0 8px 22px rgba(15, 23, 42, 0.06);
  --shadow-md: 0 18px 48px rgba(15, 23, 42, 0.1);
  --shadow-lg: 0 28px 72px rgba(30, 64, 175, 0.14);

  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  color: var(--ink);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(241, 245, 249, 0.64) 42%, rgba(248, 250, 252, 0.9)),
    linear-gradient(120deg, rgba(219, 234, 254, 0.62), rgba(236, 253, 245, 0.48) 44%, rgba(255, 247, 237, 0.42));
}

.dashboard::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(15, 23, 42, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.025) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.7), transparent 76%);
}

.topbar,
.content,
.footer {
  position: relative;
  z-index: 1;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px max(20px, calc((100vw - 1260px) / 2 + 20px));
  backdrop-filter: blur(18px) saturate(150%);
  background: rgba(248, 250, 252, 0.86);
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.82), 0 12px 34px rgba(15, 23, 42, 0.07);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: max-content;
}

.brand-dot {
  position: relative;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  overflow: hidden;
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.96), rgba(8, 145, 178, 0.9) 58%, rgba(22, 163, 74, 0.82)),
    #2563eb;
  box-shadow: inset 0 -12px 20px rgba(15, 23, 42, 0.18), 0 10px 22px rgba(37, 99, 235, 0.24);
}

.brand-dot::before,
.brand-dot::after {
  content: '';
  position: absolute;
  left: 9px;
  right: 9px;
  height: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
}

.brand-dot::before {
  top: 11px;
  box-shadow: 0 7px 0 rgba(255, 255, 255, 0.66), 0 14px 0 rgba(255, 255, 255, 0.48);
}

.brand-dot::after {
  top: 8px;
  left: 21px;
  width: 3px;
  height: 21px;
  background: rgba(255, 255, 255, 0.56);
}

.brand-title {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  line-height: 1.15;
}

.brand-subtitle {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0;
}

.topnav {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  padding: 4px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.66);
}

.topnav a {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  padding: 7px 11px;
  border-radius: 7px;
  transition: background-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.topnav a:hover {
  background: #ffffff;
  color: var(--blue);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.12);
}

.content {
  width: min(1260px, 100%);
  margin: 0 auto;
  padding: 24px 20px 48px;
  display: grid;
  gap: 24px;
}

.hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.38fr) minmax(330px, 0.72fr);
  align-items: end;
  gap: 28px;
  min-height: 360px;
  padding: 34px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(239, 246, 255, 0.94) 48%, rgba(240, 253, 250, 0.92) 100%);
  box-shadow: var(--shadow-lg);
}

.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -2;
  background-image: url('./assets/hero.png');
  background-repeat: no-repeat;
  background-position: right -12px center;
  background-size: min(510px, 48%) auto;
  opacity: 0.2;
}

.hero::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.96) 0%, rgba(255, 255, 255, 0.8) 50%, rgba(255, 255, 255, 0.54) 100%),
    linear-gradient(rgba(37, 99, 235, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(37, 99, 235, 0.05) 1px, transparent 1px);
  background-size: auto, 34px 34px, 34px 34px;
}

.hero-copy,
.hero-stats {
  position: relative;
  z-index: 1;
}

.hero h1 {
  margin: 10px 0 14px;
  max-width: 780px;
  font-size: 40px;
  line-height: 1.16;
  font-weight: 850;
}

.hero-tag {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  margin: 0;
  padding: 4px 10px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  border-radius: 8px;
  background: rgba(239, 246, 255, 0.82);
  color: var(--blue);
  font-weight: 800;
  font-size: 12px;
}

.hero-desc {
  margin: 0;
  color: #475569;
  max-width: 700px;
  font-size: 16px;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
}

.hero-actions span {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  padding: 7px 11px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.74);
  color: #334155;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
}

.hero-stats {
  display: grid;
  gap: 12px;
}

.hero-stat {
  padding: 15px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
  backdrop-filter: blur(12px);
}

.hero-stat p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}

.hero-stat strong {
  display: block;
  margin-top: 4px;
  font-size: 25px;
  line-height: 1.1;
}

.stat-bar {
  display: block;
  height: 7px;
  margin-top: 13px;
  overflow: hidden;
  border-radius: 999px;
  background: #e2e8f0;
}

.stat-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--blue), var(--cyan), var(--green));
  box-shadow: 0 0 16px rgba(37, 99, 235, 0.24);
}

.stat-bar.warning i {
  background: linear-gradient(90deg, var(--amber), var(--red));
}

.panel {
  display: grid;
  gap: 14px;
  scroll-margin-top: 92px;
  content-visibility: auto;
  contain-intrinsic-size: 820px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 2px 2px 0;
}

.panel-head h2 {
  margin: 2px 0 0;
  font-size: 21px;
  line-height: 1.2;
}

.section-kicker,
.panel-meta {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
}

.section-kicker {
  text-transform: uppercase;
}

.panel-meta {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 10px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
  color: #475569;
  white-space: nowrap;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(200px, 1fr));
  gap: 14px;
}

.two-col {
  display: grid;
  grid-template-columns: minmax(280px, 1.05fr) minmax(0, 1.95fr);
  gap: 14px;
  align-items: stretch;
}

.card {
  position: relative;
  overflow: hidden;
  background: var(--surface-strong);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 17px;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, var(--blue), var(--cyan), var(--green));
  opacity: 0.72;
}

.card:hover {
  transform: translateY(-2px);
  border-color: var(--line-strong);
  box-shadow: var(--shadow-md);
}

.card h3 {
  margin: 0 0 13px;
  font-size: 16px;
  line-height: 1.25;
}

.card-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.card-title-row h3 {
  margin-bottom: 0;
}

.card-title-row span,
.form-note,
.chart-label {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.chart-label {
  margin: 0 0 8px;
}

.chart-card {
  padding-bottom: 10px;
}

.chart {
  height: 280px;
  min-width: 0;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.9), rgba(255, 255, 255, 0.96)),
    linear-gradient(rgba(15, 23, 42, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.025) 1px, transparent 1px);
  background-size: auto, 32px 32px, 32px 32px;
}

.chart.compact {
  height: 250px;
}

.chart.tall {
  height: 360px;
}

.kv {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-height: 42px;
  padding: 10px 0;
  border-bottom: 1px dashed rgba(100, 116, 139, 0.24);
}

.kv span {
  color: #475569;
  font-weight: 650;
}

.kv b {
  font-size: 14px;
}

.kv:last-child {
  border-bottom: 0;
}

.sentiment-meter {
  position: relative;
  height: 12px;
  margin: 2px 0 11px;
  overflow: hidden;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--red) 0%, var(--amber) 48%, var(--green) 100%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.72);
}

.sentiment-meter span {
  display: block;
  width: 58%;
  height: 100%;
  border-right: 3px solid #0f172a;
  background: rgba(255, 255, 255, 0.12);
}

.asset-list {
  display: grid;
  gap: 10px;
}

.input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

input,
select {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 10px 11px;
  font-size: 14px;
  color: #172033;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
  background: #ffffff;
}

input:hover,
select:hover {
  border-color: #94a3b8;
}

input:focus,
select:focus {
  border-color: var(--blue);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14);
}

select[multiple] {
  min-height: 118px;
}

.primary-btn,
.ghost-btn {
  min-height: 38px;
  border: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 800;
  padding: 9px 14px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease, opacity 0.2s ease;
}

.primary-btn {
  color: #ffffff;
  background: linear-gradient(135deg, var(--blue), var(--cyan));
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.24);
}

.ghost-btn {
  color: #1e3a8a;
  background: #eff6ff;
  border: 1px solid rgba(37, 99, 235, 0.1);
}

.primary-btn:hover,
.ghost-btn:hover {
  transform: translateY(-1px);
}

.primary-btn:focus-visible,
.ghost-btn:focus-visible,
.topnav a:focus-visible {
  outline: 3px solid rgba(37, 99, 235, 0.24);
  outline-offset: 2px;
}

.primary-btn:disabled {
  cursor: not-allowed;
  transform: none;
  opacity: 0.55;
  box-shadow: none;
}

.full-btn {
  width: 100%;
}

.form-group {
  margin-bottom: 13px;
}

.form-note {
  margin: 8px 0 0;
  line-height: 1.5;
}

.form-group label {
  display: block;
  margin-bottom: 7px;
  font-size: 13px;
  color: #475569;
  font-weight: 800;
}

.date-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 10px;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 12px;
}

.metrics-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(5, minmax(112px, 1fr));
  gap: 10px;
}

.metric {
  min-height: 78px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  background: linear-gradient(180deg, #f8fafc, #ffffff);
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 8px;
  padding: 11px;
}

.metric p {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  font-weight: 800;
}

.metric strong {
  font-size: 21px;
  line-height: 1.2;
}

.table-wrap {
  overflow-x: auto;
}

.table-wrap.card {
  padding: 0;
}

.table-wrap.card::before {
  display: none;
}

table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

th,
td {
  text-align: center;
  padding: 13px 12px;
  border-bottom: 1px solid #e8eef6;
  white-space: nowrap;
}

th:nth-child(2),
td:nth-child(2) {
  text-align: left;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  font-size: 13px;
  color: #475569;
  background: #f8fafc;
  font-weight: 850;
}

td {
  color: #334155;
  font-weight: 650;
}

tbody tr {
  transition: background-color 0.18s ease;
}

tbody tr:hover {
  background: #f8fbff;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.check-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(100px, 1fr));
  gap: 8px;
  margin-bottom: 13px;
}

.check-list label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.08);
  color: #334155;
  font-weight: 800;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.check-list label:hover {
  border-color: rgba(37, 99, 235, 0.22);
  background: #ffffff;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
}

.check-list input {
  width: 16px;
  height: 16px;
  padding: 0;
  accent-color: var(--blue);
}

.footer {
  text-align: center;
  color: var(--muted);
  padding: 20px;
  font-size: 13px;
}

.text-positive {
  color: var(--green);
}

.text-negative {
  color: var(--red);
}

.text-warning {
  color: var(--amber);
}

@media (max-width: 1120px) {
  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .topnav {
    width: 100%;
    justify-content: flex-start;
  }

  .hero {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .hero::before {
    background-size: 560px auto;
    background-position: right -120px top 16px;
    opacity: 0.13;
  }

  .hero-stats {
    grid-template-columns: repeat(3, minmax(160px, 1fr));
  }

  .market-grid,
  .two-col,
  .chart-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: repeat(3, minmax(140px, 1fr));
  }
}

@media (max-width: 720px) {
  .topbar {
    position: static;
    padding: 14px 16px;
  }

  .brand {
    min-width: 0;
  }

  .topnav {
    flex-wrap: nowrap;
    overflow-x: auto;
    justify-content: flex-start;
    width: 100%;
    padding-bottom: 6px;
  }

  .topnav a {
    flex: 0 0 auto;
  }

  .content {
    padding: 18px 14px 36px;
    gap: 20px;
  }

  .hero {
    padding: 24px 18px;
  }

  .hero h1 {
    font-size: 30px;
  }

  .hero-desc {
    font-size: 15px;
  }

  .hero-stats,
  .metrics-grid,
  .check-list,
  .date-grid {
    grid-template-columns: 1fr;
  }

  .panel-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .panel-meta {
    white-space: normal;
  }

  .input-row {
    grid-template-columns: 1fr;
  }

  .ghost-btn {
    width: 100%;
  }

  .chart,
  .chart.tall {
    height: 300px;
  }

  .chart.compact {
    height: 240px;
  }

  .card-title-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }
}

@media (max-width: 420px) {
  .hero h1 {
    font-size: 27px;
  }

  .card {
    padding: 15px;
  }

  th,
  td {
    padding: 11px 10px;
  }
}
</style>
