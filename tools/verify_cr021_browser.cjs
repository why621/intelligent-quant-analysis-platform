/* Local real-cache/browser verification. No upstream access or injected success responses. */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')
async function main() {
  const base = 'http://127.0.0.1:8766'
  const output = path.resolve('artifacts/cr021-browser-20260910')
  await fs.mkdir(output, { recursive: true })
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
  await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort())
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  const evidence = { level: 'local browser, isolated copies of three real ETF caches; not 300-pool acceptance', scenarios: [] }
  page.setDefaultTimeout(20000)
  try {
    await page.goto(base)
    await page.waitForFunction(() => !document.querySelector('#correlation button.primary').disabled)
    const status = await (await context.request.get(base + '/api/data/status')).json()
    evidence.context = status.dataContext
    assert.ok(status.dataContext.dataVersion)
    const correlation = page.locator('#correlation')
    const got = page.waitForResponse(r => r.url().endsWith('/api/analytics/correlation') && r.request().method() === 'POST')
    await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).click()
    const response = await got
    assert.equal(response.status(), 200)
    assert.deepEqual((await response.json()).dataContext, status.dataContext)
    await correlation.locator('.chart svg').waitFor()
    await correlation.screenshot({ path: path.join(output, 'correlation.png') })
    const backtest = page.locator('#backtest')
    const submit = page.waitForResponse(r => r.url().endsWith('/api/backtests') && r.request().method() === 'POST')
    await backtest.getByRole('button', { name: '提交异步回测', exact: true }).click()
    const accepted = await submit
    assert.equal(accepted.status(), 202)
    const jobId = (await accepted.json()).jobId
    await page.waitForFunction(() => document.querySelector('#backtest .chart').textContent.includes('策略净值'))
    const job = await (await context.request.get(base + '/api/backtests/' + jobId)).json()
    assert.equal(job.status, 'succeeded')
    assert.deepEqual(job.dataContext, status.dataContext)
    const text = await backtest.locator('.chart').textContent()
    assert.ok(text.includes('策略净值'))
    assert.ok(!text.includes('基准净值'))
    await backtest.screenshot({ path: path.join(output, 'no-benchmark.png') })
    evidence.scenarios.push({ scenario: 'real correlation and no-benchmark job', jobId, status: job.status })
    const allocation = await context.request.post(base + '/api/allocation/suggestion', { data: { symbols: ['510300'], strategyId: 'ma_cross' } })
    assert.equal(allocation.status(), 503)
    assert.equal((await allocation.json()).error.code, 'DATA_STALE')
    evidence.scenarios.push({ scenario: 'old actual cache refuses current allocation', status: 503 })
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      await page.locator('nav a[href="#correlation"]').click()
      await page.waitForTimeout(700)
      const geometry = await page.evaluate(() => {
        const header = document.querySelector('.topbar')
        return { heading: document.querySelector('#correlation .panel-head').getBoundingClientRect().top,
          bottom: getComputedStyle(header).position === 'sticky' ? header.getBoundingClientRect().bottom : 0,
          overflow: document.documentElement.scrollWidth - innerWidth }
      })
      assert.ok(geometry.heading >= geometry.bottom, JSON.stringify({ width, ...geometry }))
      assert.ok(geometry.overflow <= 1, JSON.stringify({ width, ...geometry }))
      await page.screenshot({ path: path.join(output, 'viewport-' + width + '.png') })
      evidence.scenarios.push({ scenario: 'anchor and document width', width, ...geometry })
    }
    assert.deepEqual(errors, [])
    evidence.pageErrors = errors
    await fs.writeFile(path.join(output, 'evidence.json'), JSON.stringify(evidence, null, 2))
    console.log(JSON.stringify(evidence))
  } finally { await browser.close() }
}
main().catch(e => { console.error(e); process.exitCode = 1 })
