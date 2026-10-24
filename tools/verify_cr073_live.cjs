// Public read-only CR073 UI + exact static file verification. No fixture responses.
const { chromium } = require('playwright');
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const site = process.argv[2], folder = path.resolve(process.argv[3]), output = path.resolve(process.argv[4]);
assert.ok(['https://43.161.223.91/', 'https://why621.github.io/intelligent-quant-analysis-platform/'].includes(site));
const report = { site, scope: 'real public read-only UI and static hashes; no new backtests or simulations', checks: [], errors: [], hashes: {} };
const check = (name, value) => { assert.ok(value, name); report.checks.push(name); console.log('PASS', name); };
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', error => report.errors.push(error.message));
    await page.route('**/*', route => {
      const request = route.request(), url = new URL(request.url());
      if (![new URL(site).origin, 'https://43.161.223.91'].includes(url.origin)) {
        report.errors.push('Unexpected external origin ' + url.origin); return route.abort();
      }
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && !(request.method() === 'POST' && url.pathname === '/api/data/capability')) {
        report.errors.push('Prevented mutation ' + url.pathname); return route.abort();
      }
      return route.continue();
    });
    await page.goto(site, { waitUntil: 'domcontentloaded', timeout: 45000 });
    const backtest = page.locator('#backtest'), allocation = page.locator('#allocation');
    await backtest.locator('.strategy-group').first().waitFor({ timeout: 45000 });
    check('12 real strategies in 4 groups', await backtest.locator('.strategy-choice').count() === 12 && await backtest.locator('.strategy-group').count() === 4);
    check('8 simulation strategies retained', await allocation.locator('.strategy-choice').count() === 8);
    const group = backtest.locator('.strategy-group').filter({ hasText: '掩码注意力组合' });
    await group.locator('summary').focus(); await page.keyboard.press('Enter');
    await backtest.locator('input[value="portfolio_masked_ppo"]').check();
    await allocation.locator('input[value="portfolio_masked_ppo"]').waitFor();
    check('enhanced selection and linked simulation visible', await allocation.locator('input[value="portfolio_masked_ppo"]').isChecked());
    check('full model disclosure retained', (await backtest.locator('.ppo-notice').innerText()).includes('共享注意力'));
    const picker = backtest.locator('.asset-picker');
    await picker.locator('input[type=search]').fill('不存在的测试检索词');
    await picker.getByRole('button', { name: '清除筛选', exact: true }).click();
    check('real 327-asset catalog remains after filter reset', await picker.locator('.asset-option').count() === 327);
    await backtest.getByLabel('恢复任务编号', { exact: true }).fill('62d42689-ec25-463a-9f7c-3bb01c7c4a88');
    await backtest.getByRole('button', { name: '恢复查询', exact: true }).click();
    await backtest.getByText(/任务状态：已完成/).waitFor({ timeout: 45000 });
    check('existing real task restored without creating a task', (await backtest.innerText()).includes('62d42689-ec25-463a-9f7c-3bb01c7c4a88'));
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      check(`layout and navigation at ${width}`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth
        && [...document.querySelectorAll('.topbar nav a')].every(e => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })));
      await page.screenshot({ path: path.join(output, `home-${width}.png`) });
    }
    for (const file of fs.readdirSync(folder, { recursive: true }).filter(f => fs.statSync(path.join(folder, f)).isFile())) {
      const rel = file.replaceAll('\\', '/');
      const actual = await page.evaluate(async rel => {
        const response = await fetch(new URL(rel, location.href), { cache: 'reload', signal: AbortSignal.timeout(30000) });
        if (!response.ok) throw Error('Static HTTP ' + response.status);
        const digest = await crypto.subtle.digest('SHA-256', await response.arrayBuffer());
        return Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
      }, rel);
      assert.equal(actual, crypto.createHash('sha256').update(fs.readFileSync(path.join(folder, file))).digest('hex'), rel);
      report.hashes[rel] = actual;
    }
    check('12 public static hashes match release', Object.keys(report.hashes).length === 12);
    check('no runtime errors or unexpected requests', report.errors.length === 0);
  } catch (error) { report.failure = error.message; throw error; }
  finally { fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2)); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
