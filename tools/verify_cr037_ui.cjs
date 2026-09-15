const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const out = path.resolve(process.argv[2]); await fs.mkdir(out, {recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const evidence = {checks:[],errors:[]}; page.on('pageerror',e=>evidence.errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:8768');
    await page.waitForFunction(()=>document.querySelectorAll('#correlation .asset-option').length===327);
    await page.waitForFunction(()=>document.body.innerText.includes('300/327'));
    assert.ok((await page.locator('body').innerText()).includes('发布批次目标日'));
    const picker = page.locator('#correlation .asset-picker');
    await picker.getByRole('button',{name:'清空已选',exact:true}).click();
    const search = picker.getByRole('searchbox');
    for (const symbol of ['600519','600036']) {
      await search.fill(symbol); assert.match(await picker.locator('.asset-availability').innerText(),/2026-09-14/);
      await picker.getByRole('checkbox').check();
    }
    await search.fill('510300'); assert.match(await picker.locator('.asset-availability').innerText(),/更新未完成.*2026-09-09/);
    await search.fill('601238'); assert.match(await picker.locator('.asset-availability').innerText(),/停牌.*2026-09-11/);
    await search.fill('');
    const response = page.waitForResponse(r=>r.url().endsWith('/analytics/correlation')&&r.request().method()==='POST');
    await page.locator('#correlation button.primary').click(); assert.equal((await response).status(),200);
    evidence.checks.push('healthy stocks use Sep14; stale ETF shows Sep09; suspended stock shows Sep11; healthy-stock correlation HTTP200');
    await page.evaluate(()=>window.scrollTo(0,0)); await page.screenshot({path:path.join(out,'desktop.png')});
    for (const width of [820,390]) { await page.setViewportSize({width,height:950});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.screenshot({path:path.join(out,`viewport-${width}.png`)});
    }
    evidence.checks.push('desktop/tablet/mobile rendered, no horizontal overflow');
    assert.deepEqual(evidence.errors,[]); evidence.passed=true;
  } catch(e) {evidence.error=String(e);process.exitCode=1;}
  finally {await fs.writeFile(path.join(out,'browser.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));await browser.close();}
})();
