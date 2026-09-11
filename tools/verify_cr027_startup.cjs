const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')
async function main() {
  const base = 'http://127.0.0.1:8767'
  const out = path.resolve('artifacts/cr027-local-20260911')
  await fs.mkdir(out, {recursive: true})
  const browser = await chromium.launch({channel: 'msedge', headless: true})
  const evidence = []
  try {
    for (const blockCharts of [true, false]) {
      const context = await browser.newContext({viewport: {width: 1440, height: 1000}})
      await context.route('**/*', route => {
        const url = new URL(route.request().url())
        return url.origin !== base || (blockCharts && url.pathname.includes('echarts-'))
          ? route.abort() : route.continue()
      })
      const page = await context.newPage(); const errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.goto(base)
      await page.waitForFunction(() => document.querySelector('.status-card')?.textContent.includes('327') && !document.querySelector('.status-card')?.textContent.includes('连接中'))
      await page.waitForFunction(() => !document.querySelector('#correlation button.primary').disabled)
      assert.equal(await page.locator('#backtest select[multiple] option').count(), 327)
      assert.ok((await page.locator('#market').innerText()).includes('有效比较 300/300'))
      const response = page.waitForResponse(r => r.url().endsWith('/analytics/correlation') && r.request().method() === 'POST')
      await page.locator('#correlation button.primary').click()
      assert.equal((await response).status(), 200)
      await page.waitForFunction(() => document.querySelector('#correlation').textContent.includes('完整不可变发布'))
      if (blockCharts) {
        assert.equal(await page.getByText('图表加载失败', {exact: false}).count(), 3)
      } else {
        await page.locator('#correlation .chart svg').waitFor()
      }
      assert.deepEqual(errors, [])
      await page.screenshot({path: path.join(out, blockCharts ? 'chart-failure.png' : 'startup.png')})
      evidence.push({blockCharts, assetCount: 327, correlationStatus: 200, pageErrors: errors})
      await context.close()
    }
    await fs.writeFile(path.join(out, 'startup-evidence.json'), JSON.stringify({level:'local real immutable snapshot; chart failures deliberately injected', evidence}, null, 2))
    console.log(JSON.stringify(evidence))
  } finally { await browser.close() }
}
main().catch(e => {console.error(e); process.exitCode = 1})
