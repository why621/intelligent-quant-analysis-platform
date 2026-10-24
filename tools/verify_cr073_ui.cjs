// Offline UI acceptance only: synthetic API fixtures, no server or external data.
// Build apps/frontend/dist first. NODE_PATH must provide an existing Playwright.
const { chromium } = require('playwright');
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const output = path.resolve(process.argv[2] || 'artifacts/cr073-usability/browser');
const dist = path.resolve('apps/frontend/dist');
const origin = 'http://127.0.0.1:18773';
const dataContext = { publicationDate: '2026-09-07', dataVersion: 'a'.repeat(64), universeVersion: 'b'.repeat(64), consistency: 'published_snapshot' };
const assets = ['510300', '510500', '159915', '600519'].map((symbol, i) => ({ symbol, name: `测试资产${i + 1}`, active: true,
  assetType: i === 3 ? 'stock' : 'etf', exchange: 'SSE', assetId: `${i === 3 ? 'stock' : 'etf'}:SSE:${symbol}` }));
const strategies = ['ma_cross', 'momentum_reversal', 'dqn', 'ppo', 'sac', 'td3', 'portfolio_ppo', 'portfolio_sac', 'portfolio_td3',
  'portfolio_masked_ppo', 'portfolio_masked_sac', 'portfolio_masked_td3'].map((id, i) => ({ id, name: `测试策略 ${id}`,
  status: i < 2 ? 'available' : 'experimental', backtestEnabled: true, allocationEnabled: i < 2 || i > 5,
  parameterSchema: { type: 'object', properties: { lookback: { type: 'integer', default: 10, minimum: 2 } } },
  ...(i < 2 ? {} : { modelContext: { portfolioMode: i > 5 ? 'joint_portfolio' : 'legacy_independent',
    symbols: ['510300'], trainingSymbols: ['510300'], assetScope: i > 5 ? 'published_universe' : 'training_symbols',
    costPolicy: 'request_configurable', trainStartDate: '2025-01-01', trainEndDate: '2026-06-30',
    valStartDate: '2026-07-01', valEndDate: '2026-07-31', outOfSampleStartDate: '2026-08-01', minimumBars: 22 } }) }));
const report = { scope: 'offline synthetic UI fixtures; not real market, backend, or production acceptance', checks: [], errors: [] };
const check = (name, value) => { assert.ok(value, name); report.checks.push(name); console.log('PASS', name); };
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.UI_BROWSER_CHANNEL || 'msedge', headless: true, args: ['--no-proxy-server'] });
  let page;
  try {
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    page.on('pageerror', error => report.errors.push(error.message));
    let failCorrelation = false, failAllocation = false, failStartup = false;
    let releaseCorrelation, releaseAllocation;
    let correlationGate = null, allocationGate = null;
    let releaseBacktest;
    let backtestGate;
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) { report.errors.push('Blocked external request: ' + url.origin); return route.abort(); }
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (url.pathname.startsWith('/api/')) {
        if (failStartup) return reply({ error: { message: '离线测试：服务不可用' } }, 503);
        switch (url.pathname) {
          case '/api/data/status': return reply({ status: 'ready', assetCount: 4, latestTradeDate: '2026-09-07', source: '离线测试夹具', dataContext,
            components: { history: { status: 'ready' }, overview: { status: 'ready' } } });
          case '/api/assets': return reply({ items: assets, total: 4, matchedTotal: 4, offset: 0, nextOffset: null, catalogVersion: 'c'.repeat(64) });
          case '/api/strategies': return reply({ items: strategies });
          case '/api/market/overview': return reply({ tradeDate: '2026-09-07', indices: [], unavailableMetrics: [], advancing: null, declining: null, unchanged: null });
          case '/api/data/capability': return reply({ state: 'ready', issues: [], message: '离线测试：覆盖通过', dataContext });
          case '/api/strategies/ranking': {
            const request = route.request().postDataJSON();
            return reply({ request, dataContext, unavailableStrategies: [], tradingCosts: request.tradingCosts,
              evaluationStartDate: request.startDate, evaluationEndDate: request.endDate, observationCount: 42,
              items: [{ rank: 1, strategyId: 'momentum_reversal', strategyName: '测试策略 momentum_reversal',
                category: 'traditional', parameters: { lookback: 10 }, returnPct: null, maxDrawdownPct: null, sharpe: null }] });
          }
          case '/api/backtests':
            if (backtestGate) await backtestGate;
            return reply({ jobId: '12345678-1234-1234-1234-123456789012', status: 'queued', request: route.request().postDataJSON() }, 202);
          case '/api/backtests/12345678-1234-1234-1234-123456789012':
            return reply({ error: { message: '离线测试：查询中断' } }, 503);
          case '/api/analytics/correlation':
            if (correlationGate) await correlationGate;
            return failCorrelation ? reply({ error: { message: '离线测试：相关性请求失败' } }, 503)
              : reply({ symbols: ['510300', '510500', '159915'], matrix: [[1, .2, .3], [.2, 1, .4], [.3, .4, 1]], observationCount: 42, dataContext });
          case '/api/allocation/suggestion':
            if (allocationGate) await allocationGate;
            return failAllocation ? reply({ error: { message: '离线测试：模拟请求失败' } }, 503)
              : reply({ basisDate: '2026-09-07', targetDate: '2026-09-08', positions: [], cashPct: 100, dataContext, request: route.request().postDataJSON() });
          default: report.errors.push('Unexpected API: ' + url.pathname); return reply({ error: { message: 'Unexpected test request' } }, 500);
        }
      }
      const file = path.resolve(dist, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
      if (!file.startsWith(dist + path.sep)) return route.abort();
      const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };
      return route.fulfill({ path: file, contentType: types[path.extname(file)] || 'application/octet-stream' });
    });
    await page.goto(origin);
    const backtest = page.locator('#backtest'), correlation = page.locator('#correlation'), allocation = page.locator('#allocation');
    await backtest.locator('.strategy-choice').first().waitFor();
    check('all twelve strategies preserved in four groups', await backtest.locator('.strategy-choice').count() === 12 && await backtest.locator('.strategy-group').count() === 4);
    check('simulation only exposes eight supported strategies', await allocation.locator('.strategy-choice').count() === 8);
    const enhanced = backtest.locator('.strategy-group').filter({ hasText: '掩码注意力组合' });
    check('unselected advanced group initially collapsed', !await enhanced.evaluate(e => e.open));
    await enhanced.locator('summary').focus(); await page.keyboard.press('Enter');
    await backtest.locator('input[value="portfolio_masked_ppo"]').check();
    check('keyboard disclosure and model selection work', await enhanced.evaluate(e => e.open) && await backtest.locator('input[value="portfolio_masked_ppo"]').isChecked());
    await allocation.locator('input[value="portfolio_masked_ppo"]').waitFor();
    check('linked selected strategy is visible in simulation', await allocation.locator('input[value="portfolio_masked_ppo"]').isChecked());
    await enhanced.locator('summary').click();
    check('collapsed current selection remains labelled', (await backtest.locator('.strategy-selection').innerText()).includes('portfolio_masked_ppo'));
    await backtest.locator('input[value="ma_cross"]').check();
    const picker = correlation.locator('.asset-picker');
    await picker.locator('input[type=search]').fill('没有这个资产');
    check('empty search can reset with category panel closed', await picker.getByRole('button', { name: '清除筛选', exact: true }).isVisible());
    await picker.getByRole('button', { name: '清除筛选', exact: true }).click();
    check('filter reset preserves selections', await picker.locator('.asset-option').count() === 4 && await picker.locator('.selection-tray button').count() === 3);
    await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).click();
    const samples = correlation.locator('.card-head > span').filter({ hasText: '42 个样本' });
    await samples.waitFor();
    correlationGate = new Promise(resolve => { releaseCorrelation = resolve; }); failCorrelation = true;
    await correlation.getByRole('button', { name: '计算相关矩阵', exact: true }).click();
    await correlation.locator('[aria-busy=true]').waitFor();
    check('correlation retry retains result and locks dates', await samples.isVisible() && await correlation.locator('input[type=date]').first().isDisabled());
    releaseCorrelation(); correlationGate = null;
    await correlation.getByRole('alert').filter({ hasText: '已保留上一次成功结果' }).waitFor();
    await allocation.getByRole('button', { name: '生成模拟建议', exact: true }).click();
    await allocation.locator('.position-list').waitFor();
    allocationGate = new Promise(resolve => { releaseAllocation = resolve; }); failAllocation = true;
    await allocation.getByRole('button', { name: '生成模拟建议', exact: true }).click();
    await allocation.locator('[aria-busy=true]').waitFor();
    check('simulation retry retains visible weights', (await allocation.locator('.position-list').innerText()).includes('100.00%'));
    releaseAllocation(); allocationGate = null;
    await allocation.getByRole('alert').filter({ hasText: '已保留上一次成功结果' }).waitFor();
    check('simulation failure retains weights', await allocation.locator('.position-list').isVisible());
    const ranking = page.locator('#ranking');
    await ranking.getByRole('button', { name: '按当前配置计算排行', exact: true }).click();
    await ranking.getByRole('button', { name: '载入回测', exact: true }).click();
    check('ranking import moves keyboard focus to backtest and selects strategy', await backtest.evaluate(e => e === document.activeElement)
      && await backtest.locator('input[value="momentum_reversal"]').isChecked());
    backtestGate = new Promise(resolve => { releaseBacktest = resolve; });
    await backtest.getByRole('button', { name: '开始回测', exact: true }).click();
    check('running request locks numeric strategy parameters', await backtest.locator('input[name=lookback]').isDisabled());
    releaseBacktest();
    await backtest.getByRole('alert').filter({ hasText: '查询中断' }).waitFor();
    check('interrupted active job keeps draft locked but permits recovery', await backtest.locator('input[name=lookback]').isDisabled()
      && await backtest.locator('input[type=date]').first().isDisabled()
      && await backtest.getByRole('button', { name: '恢复查询', exact: true }).isEnabled());
    check('job status is translated', (await backtest.innerText()).includes('任务状态：排队中'));
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      check(`no document overflow at ${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      check(`all five navigation links fully visible at ${width}`, await page.locator('.topbar nav a').evaluateAll(links => links.length === 5
        && links.every(link => { const r = link.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom < innerHeight; })));
      await page.screenshot({ path: path.join(output, `home-${width}.png`) });
      await backtest.scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `backtest-${width}.png`) });
    }
    await page.goto(origin);
    await page.keyboard.press('Tab');
    check('first keyboard target skips to research', await page.locator('.skip-link').evaluate(e => e === document.activeElement));
    failStartup = true;
    await page.goto(origin);
    await page.getByText('数据服务暂不可用，请稍后重新加载页面', { exact: true }).waitFor();
    check('outage shows no fake strategies or asset count', await backtest.locator('.strategy-choice').count() === 0 && (await page.locator('.status-card').innerText()).includes('待加载'));
    check('zero page runtime errors and unexpected external requests', report.errors.length === 0);
  } catch (error) {
    report.failure = error.message;
    if (page) {
      await page.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
      fs.writeFileSync(path.join(output, 'failure.txt'), await page.locator('body').innerText());
    }
    throw error;
  } finally {
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
