/* Local-only browser acceptance against the built UI and real Flask worker.
 * NODE_PATH must point to an existing Playwright installation.
 * Usage: node tools/verify_m0_browser.cjs http://127.0.0.1:8765 artifacts/m0-browser
 */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:8765'
  const url = new URL(base)
  const cloudPreview = process.argv.includes('--cloud-preview')
  assert.ok(cloudPreview ? url.origin === 'http://43.161.223.91'
    : ['127.0.0.1', 'localhost'].includes(url.hostname), 'explicit preview or local-only tool')
  const output = path.resolve(process.argv[3] || 'artifacts/m0-browser')
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({ channel: process.env.M0_BROWSER_CHANNEL || 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
  await context.route('**/*', route => new URL(route.request().url()).origin === url.origin
    ? route.continue() : route.abort())
  const page = await context.newPage()
  const errors = []
  const posts = []
  const evidence = { base, browser: browser.version(), level: cloudPreview
    ? 'cloud preview browser / existing 50-asset cache and real worker; fixtures labelled separately'
    : 'local browser / real sampled caches and worker', scenarios: [] }
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => {
    if (request.method() === 'POST') posts.push({ path: new URL(request.url()).pathname, body: request.postDataJSON() })
  })
  page.setDefaultTimeout(20000)
  try {
    await page.goto(base)
    const correlation = page.locator('#correlation')
    const backtest = page.locator('#backtest')
    const submit = backtest.getByRole('button', { name: '提交异步回测', exact: true })
    await submit.waitFor()
    await page.waitForFunction(() => !document.querySelector('#backtest button.primary').disabled)
    const status = await (await context.request.get(base + '/api/data/status')).json()
    const cutoff = status.latestTradeDate
    assert.ok(cutoff)
    if (cloudPreview) {
      const catalog = await (await context.request.get(base + '/api/assets?limit=100&offset=0')).json()
      assert.equal(catalog.matchedTotal, 50)
      assert.equal(catalog.items.length, 50)
      const rankingResponse = await context.request.get(base + '/api/strategies/ranking?period=30d')
      assert.equal(rankingResponse.status(), 200)
      const ranking = await rankingResponse.json()
      assert.ok(ranking.items.length)
      const overview = await context.request.get(base + '/api/market/overview')
      assert.equal(overview.status(), 503, 'known preview limitation; not a complete MVP pass')
      evidence.preview = { catalogVersion: catalog.catalogVersion, assetCount: 50,
        cutoff, ranking, overviewStatus: overview.status() }
      await page.screenshot({ path: path.join(output, 'preview-home.png'), fullPage: true })
    }
    assert.equal(await correlation.locator('input[type=date]').nth(1).inputValue(), cutoff)
    assert.equal(await backtest.locator('input[name=shortWindow]').inputValue(), '5')
    assert.equal(await backtest.locator('input[name=longWindow]').inputValue(), '20')
    assert.equal(await backtest.locator('select').nth(2).inputValue(), '')
    assert.equal(await backtest.locator('option[value="000300"]').count(), 0)

    const correlationResponse = page.waitForResponse(response =>
      response.url().endsWith('/api/analytics/correlation') && response.request().method() === 'POST')
    await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).click()
    const response = await correlationResponse
    assert.equal(response.status(), 200)
    const matrix = await response.json()
    assert.deepEqual(matrix.symbols, ['510300', '510500', '159915'])
    assert.ok(matrix.observationCount > 200)
    await correlation.getByText(matrix.observationCount + ' 个样本', { exact: true }).waitFor()
    await correlation.locator('.chart svg').first().waitFor()
    await correlation.screenshot({ path: path.join(output, 'correlation.png') })
    evidence.scenarios.push({ scenario: 'default correlation', request: posts.at(-1), observations: matrix.observationCount })

    async function runStrategy(id, benchmark = '') {
      await backtest.locator('select').nth(1).selectOption(id)
      await backtest.locator('select').nth(2).selectOption(benchmark)
      const before = posts.filter(item => item.path === '/api/backtests').length
      const accepted = page.waitForResponse(response => response.url().endsWith('/api/backtests')
        && response.request().method() === 'POST')
      await submit.click()
      const acceptedResponse = await accepted
      assert.equal(acceptedResponse.status(), 202)
      const initial = await acceptedResponse.json()
      await backtest.locator('p.hint').filter({ hasText: new RegExp(initial.jobId + ' · succeeded') }).waitFor({ timeout: 60000 })
      const job = await (await context.request.get(base + '/api/backtests/' + initial.jobId)).json()
      assert.equal(job.status, 'succeeded')
      assert.ok(job.result.equityCurve.length > 200)
      assert.equal(job.request.strategyId, id)
      assert.equal(job.request.endDate, cutoff)
      if (benchmark) assert.equal(job.request.benchmark, benchmark)
      else {
        assert.equal('benchmark' in job.request, false)
        assert.equal(job.result.metrics.alphaPct, null)
        assert.equal(job.result.metrics.beta, null)
      }
      assert.equal(posts.filter(item => item.path === '/api/backtests').length, before + 1)
      await backtest.locator('.chart svg').first().waitFor()
      await page.waitForTimeout(1200) // Let ECharts finish its initial line animation.
      await backtest.screenshot({ path: path.join(output, id + (benchmark ? '-etf' : '') + '.png') })
      evidence.scenarios.push({ scenario: id + (benchmark ? ' ETF' : ' default'), jobId: job.jobId,
        request: job.request, points: job.result.equityCurve.length, metrics: job.result.metrics })
      return job
    }
    await runStrategy('ma_cross')
    const momentum = await runStrategy('momentum_reversal')
    assert.deepEqual(momentum.request.parameters, { lookback: 10, overboughtThreshold: 5, oversoldThreshold: -5 })

    const countBeforeReload = posts.length
    await page.reload()
    await backtest.getByLabel('恢复任务编号', { exact: true }).waitFor()
    assert.equal(await backtest.getByLabel('恢复任务编号', { exact: true }).inputValue(), momentum.jobId)
    await backtest.getByRole('button', { name: '恢复查询', exact: true }).click()
    await backtest.locator('p.hint').filter({ hasText: momentum.jobId + ' · succeeded' }).waitFor()
    assert.match(await backtest.locator('h3').innerText(), /动量反转/)
    assert.equal(posts.length, countBeforeReload)
    evidence.scenarios.push({ scenario: 'reload recovery without POST', jobId: momentum.jobId })
    await runStrategy('ma_cross', '510500')

    // CR-010: existing allocation contract, real cached history and actual API.
    const allocation = page.locator('#allocation')
    const cashInput = allocation.locator('input[type=number]')
    const allocationSubmit = allocation.getByRole('button', { name: '生成模拟建议', exact: true })
    await cashInput.fill('')
    assert.equal(await allocationSubmit.isDisabled(), true)
    await allocation.getByText('现金比例必须填写 0–100 之间的有限数值。', { exact: true }).waitFor()
    await cashInput.fill('101')
    assert.equal(await allocationSubmit.isDisabled(), true)
    evidence.scenarios.push({ scenario: 'allocation empty and out-of-range cash blocked', level: 'browser input validation' })
    for (const cash of [0, 100]) {
      await cashInput.fill(String(cash))
      const received = page.waitForResponse(response =>
        response.url().endsWith('/api/allocation/suggestion') && response.request().method() === 'POST')
      await allocationSubmit.click()
      const response = await received
      assert.equal(response.status(), 200)
      const result = await response.json()
      assert.equal(response.request().postDataJSON().cashPct, cash)
      const total = result.positions.reduce((sum, item) => sum + item.weightPct, result.cashPct)
      assert.ok(Math.abs(total - 100) < 0.01)
      const cashRow = allocation.locator('.position-list > div').filter({ has: page.getByText('现金', { exact: true }) })
      await cashRow.getByText(`${result.cashPct}%`, { exact: true }).waitFor()
      await allocation.locator('.chart svg').first().waitFor()
      await page.waitForFunction(() => [...document.querySelectorAll('#allocation .chart svg path')]
        .some(path => /a/i.test(path.getAttribute('d') || '') && path.getBBox().width > 30))
      if (cash === 100) assert.equal(result.cashPct, 100)
      await allocation.screenshot({ path: path.join(output, `allocation-${cash}.png`) })
      evidence.scenarios.push({ scenario: `allocation cash input ${cash}`, request: response.request().postDataJSON(), result })
    }
    // Empty holdings are permitted by the response contract; label this synthetic
    // boundary explicitly instead of calling it a real market-derived signal.
    await page.route('**/api/allocation/suggestion', route => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({
        basisDate: cutoff, targetDate: cutoff, strategyId: 'momentum_reversal',
        positions: [], cashPct: 100, advisoryOnly: true, disclaimer: '测试边界，不构成投资建议'
      })
    }))
    await allocationSubmit.click()
    await page.waitForFunction(() => {
      const section = document.querySelector('#allocation')
      return section.querySelectorAll('.position-list > div').length === 1
        && section.querySelector('.chart').textContent.includes('现金')
    })
    assert.equal(await allocation.getByText('生成后显示下一交易日模拟权重', { exact: true }).count(), 0)
    evidence.scenarios.push({ scenario: 'allocation empty holdings with 100% cash renders', level: 'browser fixture injection; not source evidence' })
    await page.unroute('**/api/allocation/suggestion')

    // Browser form invalid-input scenarios do not submit network requests.
    const postsBeforeInvalid = posts.length
    await backtest.locator('input[name=shortWindow]').fill('20')
    assert.equal(await submit.isDisabled(), true)
    await backtest.locator('input[name=shortWindow]').fill('5')
    const outOfRange = new Date(cutoff)
    outOfRange.setUTCDate(outOfRange.getUTCDate() + 1)
    await correlation.locator('input[type=date]').nth(1).fill(outOfRange.toISOString().slice(0, 10))
    assert.equal(await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).isDisabled(), true)
    assert.equal(posts.length, postsBeforeInvalid)
    evidence.scenarios.push({ scenario: 'invalid relationship and out-of-range date blocked in browser' })

    // Separately labelled failure injection, not real data-source evidence.
    await page.route('**/api/data/status', route => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'DATA_NOT_READY', message: 'controlled status outage' } })
    }))
    await page.reload()
    await backtest.locator('input[name=shortWindow]').waitFor()
    assert.equal(await submit.isDisabled(), true)
    assert.equal(await backtest.locator('input[type=date]').nth(1).inputValue(), '')
    assert.equal(await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).isDisabled(), true)
    evidence.scenarios.push({ scenario: 'controlled missing status blocks both forms', level: 'browser fault injection' })
    await page.unroute('**/api/data/status')
    await page.route('**/api/strategies', route => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'UPSTREAM_UNAVAILABLE', message: 'controlled metadata outage' } })
    }))
    await page.reload()
    await page.waitForFunction(() => document.querySelector('#backtest input[type=date]').value !== '')
    assert.equal(await submit.isDisabled(), true)
    assert.equal(await backtest.locator('input[name=shortWindow]').count(), 0)
    evidence.scenarios.push({ scenario: 'controlled missing metadata blocks backtest', level: 'browser fault injection' })
    await page.unroute('**/api/strategies')
    await page.route('**/api/analytics/correlation', route => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ symbols: ['510300', '510500', '159915'], observationCount: 241,
        matrix: [[1, null, null], [null, null, null], [null, null, null]] })
    }))
    await page.reload()
    await page.waitForFunction(() => !document.querySelector('#correlation button.primary').disabled)
    await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).click()
    await correlation.getByText('部分资产对无有效相关系数，留空显示；未以 0 代替。', { exact: true }).waitFor()
    await correlation.locator('.chart svg').first().waitFor()
    evidence.scenarios.push({ scenario: 'controlled nullable matrix stays blank without page error', level: 'browser fault injection' })
    assert.deepEqual(errors, [])
    evidence.pageErrors = errors
    evidence.posts = posts
    await fs.writeFile(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n')
    console.log(JSON.stringify(evidence, null, 2))
  } finally {
    await browser.close()
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
