const { chromium } = require('C:/Users/wangh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs'), path = require('path'), assert = require('node:assert/strict');
const { isDeepStrictEqual } = require('node:util');
const artifactRoot = path.resolve(process.argv[3] || 'artifacts/cr071-deploy-01/browser');
fs.mkdirSync(artifactRoot, {recursive:true});
const url = process.argv[2] || 'https://43.161.223.91/';
const base = new URL(url);
const isolated = process.argv.includes('--isolated') && base.origin === 'http://127.0.0.1:18769';
const cloud = base.origin === 'https://43.161.223.91';
const pages = base.origin === 'https://why621.github.io' && base.pathname === '/intelligent-quant-analysis-platform/';
if (!isolated && !cloud && !pages) throw Error('Only the existing cloud/Pages sites, or explicit isolated local test, are permitted.');
const mode = isolated ? 'online-isolated' : pages ? 'online-pages' : 'online-cloud';
const ledgerPath = path.join(artifactRoot, isolated ? 'isolated-mutations.json' : 'online-mutations.json');
const ledger = fs.existsSync(ledgerPath) ? JSON.parse(fs.readFileSync(ledgerPath, 'utf8')) : { jobs: {}, simulation: null };
const persistLedger = () => fs.writeFileSync(ledgerPath, JSON.stringify(ledger, null, 2));
const report = { url, source: isolated ? 'real isolated deployment candidate' : 'real deployed site; no response substitution; bounded mutations', errors: [], requests: [], checks: [] };
const save = (name, value) => fs.writeFileSync(path.join(artifactRoot, mode + '-' + name), JSON.stringify(value, null, 2));
const ok = (label, value) => { assert.ok(value, label); report.checks.push(label); console.log('PASS ' + label); };
const equal = (label, a, b) => ok(label, isDeepStrictEqual(a, b));
const symbols = ['600000', '600036', '600519', '600900', '601318', '510300', '510500', '159915', '518880', '511260'];
const oldTraining = ['000001','000002','000063','000100','000157','000166','000301','000333','000338','000408'];
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await context.newPage();
  p.on('pageerror', e => report.errors.push(e.message));
  p.on('console', m => { if (m.type() === 'error') report.errors.push(m.text()); });
  p.on('response', async r => {
    const pathname = new URL(r.url()).pathname;
    if (pathname.startsWith('/api/')) report.requests.push({ method: r.request().method(), url: r.url(), status: r.status() });
    if (pathname === '/api/backtests' && r.request().method() === 'POST') {
      try { const value = await r.json(); const strategy = r.request().postDataJSON().strategyId;
        if (ledger.jobs[strategy]) { ledger.jobs[strategy].response = value; persistLedger(); }
      } catch { /* A pending attempt stays recorded and cannot be retried silently. */ }
    }
  });
  let apiQueue = Promise.resolve();
  await p.route('**/*', async route => {
    const request = route.request(), target = new URL(request.url());
    if (!['data:', 'blob:'].includes(target.protocol) && target.origin !== base.origin && !(pages && target.origin === 'https://43.161.223.91')) {
      report.errors.push('Blocked unexpected external request: ' + request.url());
      return route.abort();
    }
    const allowedPost = ['/api/data/capability', '/api/backtests', '/api/strategies/ranking', '/api/allocation/suggestion'];
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && !(request.method() === 'POST' && allowedPost.includes(target.pathname))) {
      report.errors.push('Blocked unexpected mutation: ' + target.pathname);
      return route.abort();
    }
    if (target.pathname === '/api/backtests' && request.method() === 'POST') {
      const payload = request.postDataJSON(), strategy = payload.strategyId;
      if (!['portfolio_masked_ppo', 'portfolio_masked_td3'].includes(strategy) || ledger.jobs[strategy]) {
        report.errors.push('Prevented duplicate or unapproved backtest creation: ' + strategy);
        return route.abort();
      }
      ledger.jobs[strategy] = { attemptedAt: new Date().toISOString(), url, request: payload }; persistLedger();
    }
    if (target.pathname === '/api/allocation/suggestion' && request.method() === 'POST') {
      if (ledger.simulation) { report.errors.push('Prevented duplicate simulation computation'); return route.abort(); }
      ledger.simulation = { attemptedAt: new Date().toISOString(), url, request: request.postDataJSON() }; persistLedger();
    }
    if (target.pathname.startsWith('/api/')) { apiQueue = apiQueue.then(() => new Promise(resolve => setTimeout(resolve, 800))); await apiQueue; }
    return route.continue();
  });
  const backtest = p.locator('#backtest'), ranking = p.locator('#ranking'), allocation = p.locator('#allocation');
  const picker = backtest.locator('.asset-picker');
  const button = () => ranking.getByRole('button', { name: /按当前配置.*排行/ });
  async function choose(symbol, checked = true) {
    await picker.locator('input[type=search]').fill(symbol);
    const option = picker.locator('.asset-option').filter({ hasText: symbol });
    assert.equal(await option.count(), 1, 'unique asset option ' + symbol);
    await option.locator('input[type=checkbox]').setChecked(checked);
  }
  async function runBacktest(label) {
    const strategy = label === 'mixed-ten' ? 'portfolio_masked_ppo' : 'portfolio_masked_td3';
    const previous = ledger.jobs[strategy];
    if (previous) {
      if (!previous.response?.jobId) throw Error('An earlier accepted-state-unknown attempt exists; investigate it before another creation.');
      await backtest.getByLabel('恢复任务编号', { exact: true }).fill(previous.response.jobId);
      const ready = p.waitForResponse(async r => {
        if (!new URL(r.url()).pathname.endsWith('/backtests/' + previous.response.jobId)) return false;
        try { return ['succeeded','failed'].includes((await r.json()).status); } catch { return false; }
      }, { timeout: 120000 });
      await backtest.getByRole('button', { name: '恢复查询', exact: true }).click();
      const job = await (await ready).json();
      ok(label + ' existing acceptance job recovered without creation', job.status === 'succeeded');
      save(label + '-job.json', job);
      return { job, request: previous.request };
    }
    const accept = p.waitForResponse(r => new URL(r.url()).pathname === '/api/backtests' && r.request().method() === 'POST', { timeout: 60000 });
    const done = p.waitForResponse(async r => {
      if (!new URL(r.url()).pathname.startsWith('/api/backtests/')) return false;
      try { return ['succeeded', 'failed'].includes((await r.json()).status); } catch { return false; }
    }, { timeout: 120000 });
    accept.catch(() => {}); done.catch(() => {});
    await backtest.getByRole('button', { name: '提交异步回测', exact: true }).click({ timeout: 45000 });
    const accepted = await accept;
    ok(label + ' accepted', accepted.status() >= 200 && accepted.status() < 300);
    const request = accepted.request().postDataJSON();
    const response = await done, job = await response.json();
    ok(label + ' succeeded', job.status === 'succeeded');
    save(label + '-job.json', job);
    return { job, request };
  }
  async function runRanking(label) {
    const responsePromise = p.waitForResponse(r => new URL(r.url()).pathname === '/api/strategies/ranking' && r.request().method() === 'POST', { timeout: 60000 });
    responsePromise.catch(() => {});
    await button().click({ timeout: 45000 });
    const response = await responsePromise, result = await response.json();
    if (response.status() !== 200) save(label + '-error.json', result);
    ok(label + ' HTTP 200', response.status() === 200);
    await ranking.locator('.ranking-snapshot').waitFor();
    await p.waitForFunction(() => !document.querySelector('#ranking .ranking-stale'));
    save(label + '-ranking.json', result);
    return result;
  }
  async function changed(label, change, previous) {
    await change();
    await ranking.locator('.ranking-stale').waitFor({ timeout: 10000 });
    ok(label + ' invalidates previous ranking', await ranking.locator('.ranking-stale').isVisible());
    ok(label + ' stale ranking cannot load', await ranking.getByRole('button', { name: '载入回测' }).first().isDisabled());
    const refreshed = await runRanking(label);
    ok(label + ' refresh has distinct configuration hash', refreshed.configHash !== previous.configHash);
    return refreshed;
  }
  try {
    const initialStatus = p.waitForResponse(r => new URL(r.url()).pathname === '/api/data/status');
    const initialStrategies = p.waitForResponse(r => new URL(r.url()).pathname === '/api/strategies');
    initialStatus.catch(() => {}); initialStrategies.catch(() => {});
    await p.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
    const status = await (await initialStatus).json(), catalog = await (await initialStrategies).json();
    report.dataContext = status.dataContext;
    ok('all twelve strategies published', catalog.items.length === 12);
    const model = catalog.items.find(item => item.id === 'portfolio_masked_ppo')?.modelContext;
    assert.equal(model?.assetScope, 'published_universe', 'published scope must be available before creating any job');
    assert.equal(model?.costPolicy, 'request_configurable', 'configurable cost policy');
    ok('masked mechanism disclosed by actual API', model.representationLearning?.method === 'earnmore_inspired_masked_features');
    const prior = ledger.jobs.portfolio_masked_ppo?.request;
    const endDate = prior?.endDate || status.latestTradeDate;
    const rolling = new Date(endDate + 'T00:00:00Z'); rolling.setUTCDate(rolling.getUTCDate() - 30);
    const startDate = prior?.startDate || [model.outOfSampleStartDate, rolling.toISOString().slice(0,10)].sort().at(-1);
    report.requestWindow = { startDate, endDate, latestTradeDate: status.latestTradeDate };
    await backtest.locator('input[value="portfolio_masked_ppo"]').waitFor({ timeout: 60000 });
    ok('published asset catalog is 327', await picker.locator('.asset-option').count() === 327);
    ok('startup does not call legacy 510300 ranking', !report.requests.some(r => r.method === 'GET' && new URL(r.url).pathname === '/api/strategies/ranking'));
    ok('startup does not implicitly calculate research ranking', !report.requests.some(r => r.method === 'POST' && new URL(r.url).pathname === '/api/strategies/ranking'));
    await p.mouse.move(320, 250); await p.waitForTimeout(100);
    ok('bright circle cursor retained', await p.locator('html').getAttribute('data-quant-cursor') === 'on');
    const filter = picker.locator('.filter-disclosure');
    await filter.click(); await p.waitForTimeout(350);
    ok('filter expands with interactive content', await filter.getAttribute('aria-expanded') === 'true' && !await picker.locator('.filter-expansion').evaluate(e => e.inert));
    await filter.click(); await p.waitForTimeout(350);
    ok('collapsed filter contents are inert', await picker.locator('.filter-expansion').evaluate(e => e.inert));
    await backtest.locator('input[value="portfolio_masked_ppo"]').check();
    await picker.getByRole('button', { name: '清空已选', exact: true }).click();
    for (const symbol of symbols) await choose(symbol);
    await picker.locator('input[type=search]').fill('');
    ok('ten selected assets are all outside original ten-stock pool', symbols.length === 10 && symbols.every(s => !oldTraining.includes(s)) && await picker.locator('.selection-tray small').count() === 10);
    await backtest.getByRole('button', { name: '使用当前可用样本外日期区间', exact: true }).click();
    await backtest.getByLabel('开始日期', { exact: true }).fill(startDate);
    await backtest.getByLabel('结束日期', { exact: true }).fill(endDate);
    await backtest.getByLabel('初始资金（元）', { exact: true }).fill('150000');
    await backtest.getByLabel('预留现金（%）', { exact: true }).fill('7.5');
    await backtest.getByLabel('佣金（% / 单边）', { exact: true }).fill('0.08');
    ok('full-universe joint model disclosure', (await backtest.locator('.ppo-notice').innerText()).includes('当前发布目录中的股票和 ETF'));
    ok('evaluation aggregate source is disclosed', (await backtest.locator('.joint-evaluation').innerText()).includes('三组独立十资产参考组合'));
    const first = await runBacktest('mixed-ten');
    equal('backtest result uses current research data version', first.job.result.dataContext.dataVersion, status.dataContext.dataVersion);
    equal('joint backtest preserves ten selected assets', first.request.symbols, symbols);
    ok('joint backtest shared execution and published universe', first.request.portfolioMode === 'shared_account' && first.job.result.modelContext.portfolioMode === 'joint_portfolio' && first.job.result.modelContext.assetScope === 'published_universe');
    ok('ten positions share one portfolio ledger', first.job.result.accountCurve.at(-1).positions.length === 10);
    equal('requested transaction costs preserved', first.job.request.tradingCosts, first.request.tradingCosts);
    ok('transaction cost ledger recorded', Number.isFinite(first.job.result.costSummary.totalTradingCostCny));
    let ranked = await runRanking('initial');
    equal('ranking request exactly matches backtest request', ranked.request, first.request);
    for (const id of ['ma_cross', 'momentum_reversal', 'portfolio_ppo', 'portfolio_sac', 'portfolio_td3', 'portfolio_masked_sac', 'portfolio_masked_ppo', 'portfolio_masked_td3']) ok('comparable ranking includes ' + id, ranked.items.some(i => i.strategyId === id));
    const matched = ranked.items.find(i => i.strategyId === first.request.strategyId);
    equal('ranking and same-request backtest metrics are identical', matched.metrics, first.job.result.metrics);
    equal('ranking and same-request backtest cost ledger are identical', matched.costSummary, first.job.result.costSummary);
    ok('every row discloses exact strategy parameters', ranked.items.every(i => i.parameters && Object.keys(i.parameters).length > 0));
    report.initialRanking = { configHash: ranked.configHash, items: ranked.items.map(i => ({ strategyId: i.strategyId, returnPct: i.returnPct })) };
    ranked = await changed('fee-change', () => backtest.getByLabel('佣金（% / 单边）', { exact: true }).fill('0.12'), ranked);
    equal('changed fee survives ranking request', ranked.request.tradingCosts.commissionPct, 0.12);
    ranked = await changed('cash-change', () => backtest.getByLabel('预留现金（%）', { exact: true }).fill('17.5'), ranked);
    equal('changed reserved cash survives ranking request', ranked.request.cashPct, 17.5);
    ranked = await changed('date-change', () => backtest.getByLabel('结束日期', { exact: true }).fill(new Date(Date.parse(endDate + 'T00:00:00Z') - 86400000).toISOString().slice(0,10)), ranked);
    equal('changed date survives ranking request', ranked.request.endDate, new Date(Date.parse(endDate + 'T00:00:00Z') - 86400000).toISOString().slice(0,10));
    ranked = await changed('asset-change', async () => { await choose('518880', false); await choose('512880'); await picker.locator('input[type=search]').fill(''); }, ranked);
    ok('asset replacement survives ranking snapshot', ranked.request.symbols.length === 10 && ranked.request.symbols.includes('512880') && !ranked.request.symbols.includes('518880'));
    ok('configuration changes produce different measured returns', ranked.items.some(item => report.initialRanking.items.some(before => before.strategyId === item.strategyId && before.returnPct !== item.returnPct)));
    const traditional = ranked.items.find(i => i.strategyId === 'portfolio_masked_td3');
    const row = ranking.locator('tbody tr').filter({ hasText: traditional.strategyName });
    await row.getByRole('button', { name: '载入回测', exact: true }).click();
    ok('ranking import selects the exact strategy', await backtest.locator('input[value="portfolio_masked_td3"]').isChecked());
    equal('ranking import keeps exact start date', await backtest.getByLabel('开始日期', { exact: true }).inputValue(), ranked.request.startDate);
    equal('ranking import keeps exact end date', await backtest.getByLabel('结束日期', { exact: true }).inputValue(), ranked.request.endDate);
    const second = await runBacktest('ranking-loaded');
    equal('imported backtest metrics equal selected ranking row', second.job.result.metrics, traditional.metrics);
    for (const key of ['symbols','startDate','endDate','initialCapitalCny','cashPct','tradingCosts','benchmarkMode','adjust']) equal('ranking import preserves ' + key, second.request[key], ranked.request[key]);
    equal('ranking import preserves selected row parameters', second.request.parameters, traditional.parameters);
    if (!ledger.simulation) {
    const simPromise = p.waitForResponse(r => new URL(r.url()).pathname === '/api/allocation/suggestion', { timeout: 60000 });
    await allocation.getByRole('button', { name: '生成模拟建议', exact: true }).click({ timeout: 45000 });
    const simResponse = await simPromise, simulated = await simResponse.json();
    ok('linked simulation succeeds', simResponse.status() === 200);
    ledger.simulation.response = simulated; persistLedger();
    save('linked-allocation.json', simulated);
    for (const key of ['symbols','strategyId','parameters','startDate','initialCapitalCny','cashPct','tradingCosts']) equal('linked simulation shares ' + key, simulated.request[key], second.request[key]);
    ok('simulated asset and cash weights sum to 100', Math.abs(simulated.cashPct + simulated.positions.reduce((sum,x) => sum + x.weightPct, 0) - 100) < 1e-6);
    } else {
      ok('Pages/retry does not repeat simulation computation', Boolean(ledger.simulation.response));
      for (const key of ['symbols','strategyId','parameters','startDate','initialCapitalCny','cashPct','tradingCosts']) equal('recorded simulation shares ' + key, ledger.simulation.response.request[key], second.request[key]);
      ok('simulation form still inherits loaded strategy', await allocation.locator('input[value="portfolio_masked_td3"]').isChecked());
    }
    await runRanking('final-current');
    for (const width of [1440,390,320]) {
      await p.setViewportSize({ width, height: 1000 }); await p.waitForTimeout(400);
      ok('no page overflow at ' + width, await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      await ranking.screenshot({ path: path.join(artifactRoot, mode + '-ranking-' + width + '.png') });
      await backtest.locator('.backtest-workspace > article').nth(1).screenshot({ path: path.join(artifactRoot, mode + '-backtest-' + width + '.png') });
    }
    await p.setViewportSize({ width: 1440, height: 1000 });
    await p.getByRole('button', { name: '动态效果 开', exact: true }).click();
    await p.getByRole('button', { name: '圆环光标 开', exact: true }).click();
    ok('motion and cursor switches can disable effects', await p.getByRole('button', { name: '动态效果 关', exact: true }).count() === 1 && await p.getByRole('button', { name: '圆环光标 关', exact: true }).count() === 1);
    await p.reload({ waitUntil: 'networkidle', timeout: 90000 });
    ok('effect preferences persist after reload', await p.getByRole('button', { name: '动态效果 关', exact: true }).count() === 1 && await p.getByRole('button', { name: '圆环光标 关', exact: true }).count() === 1);
    await p.getByRole('button', { name: '动态效果 关', exact: true }).click();
    await p.getByRole('button', { name: '圆环光标 关', exact: true }).click();
    await p.emulateMedia({ reducedMotion: 'reduce' });
    ok('reduced-motion accessibility retained', await p.getByRole('button', { name: '系统静态模式', exact: true }).isDisabled());
    report.scripts = await p.locator('script[src]').evaluateAll(nodes => nodes.map(node => node.src));
    ok('browser runtime clean', report.errors.length === 0);
    ok('all actual API requests successful', report.requests.every(r => r.status >= 200 && r.status < 300));
    report.status = 'passed';
  } catch (error) {
    report.status = 'failed'; report.error = error.stack; process.exitCode = 1;
    await p.screenshot({ path: path.join(artifactRoot, mode + '-failed.png'), fullPage: false }).catch(() => {});
  } finally {
    save('browser.json', report); console.log(JSON.stringify(report, null, 2)); await browser.close();
  }
})();
