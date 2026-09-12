const {chromium}=require('playwright')
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path')
async function main(){
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--proxy-bypass-list=43.161.223.91']})
 const page=await browser.newPage({viewport:{width:1440,height:1050}})
 const base='https://why621.github.io/intelligent-quant-analysis-platform/',api='https://43.161.223.91/api'
 const out=path.resolve('artifacts/cr027-pages-20260911/browser'),e={level:'real Pages follow-up; backend IP direct route; reuses existing jobs',errors:[],failed:[],newBacktestPosts:0}
 page.on('pageerror',x=>e.errors.push(x.message));page.on('requestfailed',r=>e.failed.push({url:r.url(),error:r.failure()}))
 page.on('request',r=>{if(r.url()===api+'/backtests'&&r.method()==='POST')e.newBacktestPosts++})
 page.setDefaultTimeout(45000)
 try{
  await page.goto(base)
  const backtest=page.locator('#backtest')
  for(const id of ['745da643-ff3d-475a-8633-44260aa24887','6c66e3cc-1445-4329-a1ff-f7f802c9e8f3']){
   await backtest.locator('input').last().fill(id)
   const received=page.waitForResponse(r=>r.url()===api+'/backtests/'+id)
   await backtest.getByRole('button',{name:'恢复查询',exact:true}).click()
   const r=await received;assert.equal(r.status(),200);const job=await r.json();assert.equal(job.status,'succeeded')
   e.jobs=e.jobs||[];e.jobs.push({jobId:id,strategy:job.request.strategyId,status:job.status,dataContext:job.dataContext})
   await page.waitForFunction(()=>document.querySelector('#backtest .chart').textContent.includes('策略净值'))
  }
  await page.reload()
  await backtest.getByRole('button',{name:'恢复查询',exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('#backtest .chart').textContent.includes('策略净值'))
  assert.equal(e.newBacktestPosts,0);e.recovery=true
  await backtest.screenshot({path:path.join(out,'restored-backtest.png')})
  await page.waitForFunction(()=>!document.querySelector('#allocation button.primary').disabled)
  const received=page.waitForResponse(r=>r.url()===api+'/allocation/suggestion'&&r.request().method()==='POST')
  await page.locator('#allocation button.primary').click()
  const r=await received;assert.equal(r.status(),503);const result=await r.json();assert.equal((result.error||result).code,'DATA_STALE')
  await page.locator('#allocation .error').waitFor();e.allocation={status:503,code:'DATA_STALE'}
  await page.locator('#allocation').screenshot({path:path.join(out,'allocation-stale.png')})
  for(const width of [1440,820,390]){
   await page.setViewportSize({width,height:1000});await page.locator('nav a[href="#correlation"]').click();await page.waitForTimeout(700)
   const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,top:document.querySelector('#correlation .panel-head').getBoundingClientRect().top,bottom:getComputedStyle(document.querySelector('.topbar')).position==='sticky'?document.querySelector('.topbar').getBoundingClientRect().bottom:0}))
   assert.ok(geometry.overflow<=1);assert.ok(geometry.top>=geometry.bottom)
   await page.screenshot({path:path.join(out,'viewport-'+width+'.png')});e.widths=e.widths||[];e.widths.push({width,...geometry})
  }
  assert.deepEqual(e.errors,[]);assert.deepEqual(e.failed,[]);e.passed=true
 }catch(err){e.failure=err.message;e.backtestText=(await backtestText(page));process.exitCode=1}
 finally{await fs.writeFile(path.join(out,'recovery-evidence.json'),JSON.stringify(e,null,2));console.log(JSON.stringify(e));await browser.close()}
}
async function backtestText(page){return page.locator('#backtest .error').allTextContents()}
main().catch(e=>{console.error(e);process.exitCode=1})
