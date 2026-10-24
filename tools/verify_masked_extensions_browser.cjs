// Local real-model checks only. No production hosts, mocked responses or orders.
const { chromium } = require('C:/Users/wangh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs'), path = require('path'), assert = require('node:assert/strict');
const output = path.resolve(process.argv[2]);
fs.mkdirSync(output, {recursive:true});
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true,args:['--no-proxy-server']});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const report = {scope:'local real frozen data; historical allocation clock; not cloud acceptance', checks:[], errors:[]};
  const check = (name, value) => { assert.ok(value, name); report.checks.push(name); };
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('console', m => { if(m.type()==='error') report.errors.push(m.text()); });
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:18771' && !['data:','blob:'].includes(url.protocol)) {
      report.errors.push('Unexpected external request '+url.origin);
      return route.abort();
    }
    return route.continue();
  });
  const backtest = page.locator('#backtest'), ranking = page.locator('#ranking'), allocation = page.locator('#allocation');
  try {
    const ready = page.waitForResponse(r=>r.url().endsWith('/api/strategies'));
    await page.goto('http://127.0.0.1:18771/',{waitUntil:'networkidle'});
    const catalog = (await (await ready).json()).items;
    check('all twelve strategies retained', catalog.length===12);
    for(const id of ['ppo','sac','dqn','td3','portfolio_ppo','portfolio_sac','portfolio_td3','portfolio_masked_sac']) {
      check('existing selectable '+id, await backtest.locator(`input[value="${id}"]`).count()===1);
    }
    for(const id of ['portfolio_masked_ppo','portfolio_masked_td3']) {
      const enhanced = backtest.locator('.strategy-group').filter({ hasText: '掩码注意力组合' });
      if (await enhanced.count() && !await enhanced.evaluate(e => e.open)) await enhanced.locator('summary').click();
      await backtest.locator(`input[value="${id}"]`).check();
      check(id+' mechanism disclosure', (await backtest.locator('.ppo-notice').innerText()).includes('共享注意力'));
      const picker = backtest.locator('.asset-picker');
      await picker.getByRole('button',{name:'清空已选',exact:true}).click();
      for(const symbol of ['600000','600036','600519','600900','601318','510300','510500','159915','518880','511260']) {
        await picker.locator('input[type=search]').fill(symbol);
        await picker.locator('.asset-option').filter({hasText:symbol}).locator('input[type=checkbox]').check();
      }
      await picker.locator('input[type=search]').fill('');
      await backtest.getByRole('button',{name:'使用当前可用样本外日期区间',exact:true}).click();
      await backtest.getByLabel('预留现金（%）',{exact:true}).fill('15');
      const done = page.waitForResponse(async r=>{
        if(!r.url().includes('/api/backtests/'))return false;
        return ['succeeded','failed'].includes((await r.json()).status);
      },{timeout:120000});
      await backtest.getByRole('button',{name:/^(开始回测|提交异步回测)$/}).click();
      const job = await (await done).json();
      check(id+' actual ten-asset shared account',job.status==='succeeded' && job.result.accountCurve.at(-1).positions.length===10);
      const ranked = page.waitForResponse(r=>r.url().endsWith('/api/strategies/ranking') && r.request().method()==='POST',{timeout:60000});
      await ranking.getByRole('button',{name:/按当前配置.*排行/}).click();
      const response = await ranked, result = await response.json();
      check(id+' ranking success',response.status()===200 && result.items.length===8);
      assert.deepEqual(result.items.find(x=>x.strategyId===id).metrics,job.result.metrics);
      check(id+' ranking metrics equal actual backtest',true);
      check(id+' simulation selection linked',await allocation.locator(`input[value="${id}"]`).isChecked());
      const simulated = page.waitForResponse(r=>r.url().endsWith('/api/allocation/suggestion'),{timeout:60000});
      await allocation.getByRole('button',{name:'生成模拟建议',exact:true}).click();
      const simResponse = await simulated, sim = await simResponse.json();
      check(id+' simulation success',simResponse.status()===200);
      for(const key of ['symbols','strategyId','parameters','startDate','initialCapitalCny','cashPct','tradingCosts']) assert.deepEqual(sim.request[key],job.request[key]);
      check(id+' simulation configuration exact',true);
      fs.writeFileSync(path.join(output,id+'.json'),JSON.stringify({job,ranking:result,simulation:sim},null,2));
    }
    for(const width of [1440,390,320]) {
      await page.setViewportSize({width,height:1000});
      await page.waitForTimeout(300);
      check('no overflow '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.screenshot({path:path.join(output,'viewport-'+width+'.png')});
    }
    check('no browser runtime errors',report.errors.length===0);
    report.passed=true;
  } catch(e) {
    report.passed=false;report.error=e.stack;process.exitCode=1;
    await page.screenshot({path:path.join(output,'failed.png')});
  } finally {
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
