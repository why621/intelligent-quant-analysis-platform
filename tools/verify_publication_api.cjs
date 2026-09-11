const assert=require('node:assert/strict')
module.exports=async function verify(request,base,status) {
  assert.ok(new URL(base).hostname==='127.0.0.1'||['https://43.161.223.91','http://43.161.223.91'].includes(base))
  async function get(path) {
    const response=await request.get(base+path)
    assert.equal(response.status(),200,await response.text())
    return response.json()
  }
  async function post(path,data,expected=200) {
    const response=await request.post(base+path,{data})
    assert.equal(response.status(),expected,await response.text())
    return response.json()
  }
  const coverage=await get('/api/data/coverage')
  assert.equal(coverage.items.length,327)
  assert.equal(coverage.memberCount,300)
  assert.equal(coverage.etfCount,27)
  assert.deepEqual(coverage.dataContext,status.dataContext)
  const overview=await get('/api/market/overview')
  assert.equal(overview.scope,'csi300_current_constituents')
  assert.equal(overview.advancing+overview.declining+overview.unchanged+overview.suspended,300)
  assert.deepEqual(overview.dataContext,status.dataContext)
  const catalog=[]
  for(let offset=0;offset<327;offset+=100) {
    const value=await get('/api/assets?limit=100&offset='+offset)
    assert.equal(value.matchedTotal,327)
    catalog.push(...value.items)
  }
  assert.equal(new Set(catalog.map(a=>a.assetId)).size,327)
  const symbols=['600438','600958','601059','601995','688012','688072','688521','001280','002049','300442']
  const dates={startDate:'2025-09-09',endDate:'2026-09-09'}
  const correlation=await post('/api/analytics/correlation',{symbols,...dates,adjust:'qfq',returnType:'simple'})
  assert.equal(correlation.matrix.length,10)
  assert.deepEqual(correlation.dataContext,status.dataContext)
  const ranking=await get('/api/strategies/ranking?period=30d')
  assert.equal(ranking.items.length,2)
  assert.deepEqual(ranking.dataContext,status.dataContext)
  const strategies=await get("/api/strategies")
  const jobs=[]
  for(const strategyId of ['ma_cross','momentum_reversal']) {
    const schema=strategies.items.find(s=>s.id===strategyId).parameterSchema
    const parameters=Object.fromEntries(Object.entries(schema.properties).map(([k,r])=>[k,r.default]))
    const accepted=await post('/api/backtests',{parameters,symbols:['600438','001280'],strategyId,...dates,benchmark:'index:CSI:000300'},202)
    let job
    for(let n=0;n<60;n++) {
      job=await get('/api/backtests/'+accepted.jobId)
      if(!['queued','running'].includes(job.status)) break
      await new Promise(resolve=>setTimeout(resolve,500))
    }
    assert.equal(job.status,'succeeded',JSON.stringify(job))
    assert.deepEqual(job.dataContext,status.dataContext)
    assert.equal(job.result.assumptions.benchmarkReturnBasis,'price_index')
    jobs.push({jobId:job.jobId,strategyId,status:job.status,metrics:job.result.metrics})
  }
  return {overview,assetCount:catalog.length,correlationObservations:correlation.observationCount,ranking,jobs}
}
