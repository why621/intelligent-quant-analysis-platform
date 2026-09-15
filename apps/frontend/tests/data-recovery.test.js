import test from 'node:test'
import assert from 'node:assert/strict'
import { recoveryOptions } from '../src/dashboard/data-recovery.js'
const request = { module: 'correlation', symbols: ['159915','600026','600027'], startDate: '2025-09-14', endDate: '2026-09-14' }
const result = { state: 'unavailable', issues: [{symbol:'159915',code:'DATA_GAP'}] }
const assets = request.symbols.map(symbol => ({symbol,availability:{lastTradeDate:symbol==='159915'?'2026-09-11':'2026-09-14'}}))
test('mixed selected assets offer explicit subset and historical end without mutating selection', () => {
 const before=JSON.stringify(request);const options=recoveryOptions(request,result,assets)
 assert.deepEqual(options.map(o=>o.patch),[{symbols:['600026','600027']},{endDate:'2026-09-11'}])
 assert.equal(JSON.stringify(request),before)
})
test('correlation never proposes fewer than two and global issues do not promise a healthy subset',()=>{
 assert.equal(recoveryOptions({...request,symbols:['159915','600026']},result).length,0)
 assert.equal(recoveryOptions(request,{...result,issues:[...result.issues,{symbol:null,code:'DATA_STALE'}]}).length,0)
})
test('current allocation never falls back to historical dates',()=>{
 const options=recoveryOptions({...request,module:'allocation'},result,assets)
 assert.deepEqual(options.map(o=>o.patch),[{symbols:['600026','600027']}])
})
test('missing comparison benchmark can be explicitly cancelled',()=>{
 const options=recoveryOptions({...request,module:'backtest',symbols:['600026'],benchmark:'159915'},result,assets)
 assert.deepEqual(options.map(o=>o.patch),[{benchmark:null},{endDate:'2026-09-11'}])
})
test('unknown histories or invalid date range produce no speculative date adjustment',()=>{
 assert.equal(recoveryOptions(request,result,[]).some(o=>o.patch.endDate),false)
 assert.equal(recoveryOptions({...request,startDate:'2026-09-12'},result,assets).some(o=>o.patch.endDate),false)
 assert.deepEqual(recoveryOptions(request,{state:'ready',issues:[]},assets),[])
})
