const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')
async function main() {
 const base='https://why621.github.io/intelligent-quant-analysis-platform/'
 const api='https://43.161.223.91/api'
 const out=path.resolve('artifacts/cr027-pages-20260911/browser')
 await fs.mkdir(out,{recursive:true})
 const browser=await chromium.launch({channel:'msedge',headless:true})
 const context=await browser.newContext({viewport:{width:1440,height:1050}})
 const page=await context.newPage()
 const evidence={level:'real GitHub Pages to cloud HTTPS browser',base,api,scenarios:[],pageErrors:[],failedRequests:[],unexpectedOrigins:[]}
 page.on('pageerror',e=>evidence.pageErrors.push(e.message))
 page.on('requestfailed',r=>evidence.failedRequests.push({url:r.url(),error:r.failure()}))
 page.on('request',r=>{if(!['https://why621.github.io','https://43.161.223.91'].includes(new URL(r.url()).origin))evidence.unexpectedOrigins.push(r.url())})
 page.setDefaultTimeout(45000)
 try {
  const statusResponse=page.waitForResponse(r=>r.url()===api+'/data/status')
  const rankingResponse=page.waitForResponse(r=>r.url().startsWith(api+'/strategies/ranking')); rankingResponse.catch(()=>{})
  await page.goto(base,{timeout:45000})
  const sr=await statusResponse; assert.equal(sr.status(),200)
  const status=await sr.json(); assert.equal(status.assetCount,327); evidence.context=status.dataContext
  await page.waitForFunction(()=>document.querySelector('#correlation button.primary')&&!document.querySelector('#correlation button.primary').disabled)
  await page.waitForFunction(()=>document.querySelectorAll('#backtest select[multiple] option').length===327)
  assert.equal(await page.locator('#backtest select[multiple] option').count(),327)
  assert.ok((await page.locator('#market').innerText()).includes('有效比较 300/300'))
  const rr=await rankingResponse;assert.equal(rr.status(),200)
  const ranks=await rr.json();assert.equal(ranks.items.length,2);assert.deepEqual(ranks.dataContext,status.dataContext)
  evidence.scenarios.push('327 catalog, 300 overview, two strategy rankings via browser CORS')
  await page.screenshot({path:path.join(out,'overview.png')})
  const symbols=await page.locator('#backtest select[multiple] option').evaluateAll(options=>options.filter(o=>o.value.startsWith('600')).slice(0,10).map(o=>o.value))
  const cor=page.locator('#correlation')
  while(await cor.locator('input[maxlength="6"]').count()<10)await cor.getByRole('button',{name:'添加资产',exact:true}).click()
  for(let i=0;i<10;i++)await cor.locator('input[maxlength="6"]').nth(i).fill(symbols[i])
  const response=page.waitForResponse(r=>r.url()===api+'/analytics/correlation'&&r.request().method()==='POST')
  await cor.locator('button.primary').click()
  const cr=await response;assert.equal(cr.status(),200)
  const matrix=await cr.json();assert.equal(matrix.matrix.length,10);assert.deepEqual(matrix.dataContext,status.dataContext)
  await cor.locator('.chart svg').waitFor()
  evidence.scenarios.push({name:'ten asset correlation / 45 pairs',symbols,observations:matrix.observationCount})
  await cor.screenshot({path:path.join(out,'correlation.png')})
  for(const strategy of ['ma_cross','momentum_reversal']) {
   const section=page.locator('#backtest')
   await section.locator('select:not([multiple])').first().selectOption(strategy)
   const accepted=page.waitForResponse(r=>r.url()===api+'/backtests'&&r.request().method()==='POST')
   await section.getByRole('button',{name:'提交异步回测',exact:true}).click()
   const ar=await accepted;assert.equal(ar.status(),202)
   const jobId=(await ar.json()).jobId
   await page.waitForFunction(()=>document.querySelector('#backtest .chart').textContent.includes('策略净值'))
   // The page's own polling is the acceptance source, not a scripted API substitute.
   await page.waitForFunction(id=>document.querySelector('#backtest').textContent.includes(id),jobId)
   evidence.scenarios.push({name:'UI backtest',strategy,jobId})
  }
  let duplicatePosts=0
  page.on('request',r=>{if(r.url()===api+'/backtests'&&r.method()==='POST')duplicatePosts++})
  await page.reload()
  await page.locator('#backtest').getByRole('button',{name:'恢复查询',exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('#backtest .chart').textContent.includes('策略净值'))
  assert.equal(duplicatePosts,0)
  evidence.scenarios.push('reload restores backtest without duplicate POST')
  await page.locator('#backtest').screenshot({path:path.join(out,'backtest.png')})
  const allocation=page.waitForResponse(r=>r.url()===api+'/allocation/suggestion'&&r.request().method()==='POST')
  await page.locator('#allocation button.primary').click()
  const ar=await allocation;assert.equal(ar.status(),503)
  const error=await ar.json();assert.equal((error.error||error).code,'DATA_STALE')
  await page.locator('#allocation .error').waitFor()
  evidence.scenarios.push({name:'stale allocation is explicitly rejected',status:503,code:'DATA_STALE'})
  await page.locator('#allocation').screenshot({path:path.join(out,'allocation-stale.png')})
  for(const width of [1440,820,390]) {
   await page.setViewportSize({width,height:1000})
   await page.locator('nav a[href="#correlation"]').click()
   await page.waitForTimeout(700)
   const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,heading:document.querySelector('#correlation .panel-head').getBoundingClientRect().top,header:document.querySelector('.topbar').getBoundingClientRect().bottom}))
   assert.ok(geometry.overflow<=1)
   await page.screenshot({path:path.join(out,'viewport-'+width+'.png')})
   evidence.scenarios.push({width,...geometry})
  }
  assert.deepEqual(evidence.pageErrors,[]);assert.deepEqual(evidence.unexpectedOrigins,[]);assert.deepEqual(evidence.failedRequests,[])
  evidence.passed=true
 } catch(e) {evidence.failure=e.message;evidence.body=(await page.locator('body').innerText()).slice(0,3500);await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});process.exitCode=1}
 finally {await fs.writeFile(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));await browser.close()}
}
main().catch(e=>{console.error(e);process.exitCode=1})
