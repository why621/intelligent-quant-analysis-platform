import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useBacktest } from '../src/dashboard/use-backtest.js'
import { useAllocation } from '../src/dashboard/use-allocation.js'

const ppo = enabled => ({id:'ppo', name:'PPO', status:'experimental', backtestEnabled:enabled,
  parameterSchema:{type:'object',required:['modelRef'],properties:{modelRef:{type:'string',title:'模型',enum:['ppo-reviewed'],default:'ppo-reviewed'}}},
  modelContext:{assetScope:'published_universe',trainingSymbols:['510300'],symbols:['510300'],trainEndDate:'2026-06-30',outOfSampleStartDate:'2026-07-01'}})
function setup(t, enabled = true) {
  const scope = effectScope(); t.after(() => scope.stop())
  const strategies = ref([ppo(enabled)])
  const state = scope.run(() => useBacktest(strategies,ref({status:'ready',latestTradeDate:'2026-09-18'}),ref([]),{},null))
  state.strategyId.value = 'ppo'
  return {state,strategies,scope}
}
test('explicit experimental PPO supports model select and sample-out range', t => {
  const {state} = setup(t)
  assert.deepEqual(state.parameters.value,{modelRef:'ppo-reviewed'})
  assert.match(state.validationError.value,/训练区间/)
  state.applyModelRange()
  assert.equal(state.startDate.value,'2026-07-01')
  assert.equal(state.endDate.value,'2026-09-18')
  assert.equal(state.canSubmit.value,true)
  state.parameters.value.modelRef = '../other'
  assert.match(state.validationError.value,/已部署/)
})
test('other assets are accepted while disabled PPO remains blocked', t => {
  const {state,strategies} = setup(t)
  state.applyModelRange(); state.symbols.value=['600519']
  assert.equal(state.canSubmit.value,true)
  strategies.value=[ppo(false)]
  assert.equal(state.availableStrategies.value.length,0)
  assert.equal(state.canSubmit.value,false)
})
test('experimental capability does not enable allocation', t => {
  const {scope,strategies} = setup(t)
  const allocation=scope.run(()=>useAllocation(strategies,{}))
  assert.equal(allocation.availableStrategies.value.length,0)
})

test('sample-out button preserves a mixed portfolio', t => {
  const {state}=setup(t)
  state.symbols.value=['512100','600519','510300']
  state.applyModelRange()
  assert.deepEqual(state.symbols.value,['512100','600519','510300'])
  assert.equal(state.canSubmit.value,true)
})
test('legacy model scope still enforces explicit asset list', t => {
  const {state,strategies}=setup(t)
  delete strategies.value[0].modelContext.assetScope
  state.applyModelRange(); state.symbols.value=['512100']
  assert.match(state.validationError.value,/510300/)
})
test('date shortcut waits for publication and never writes an empty end date', t => {
  const scope=effectScope();t.after(()=>scope.stop())
  const status=ref({status:'updating',latestTradeDate:null})
  const state=scope.run(()=>useBacktest(ref([ppo(true)]),status,ref([]),{},null))
  state.strategyId.value='ppo';state.symbols.value=['512100']
  state.applyModelRange()
  assert.equal(state.startDate.value,'')
  status.value={status:'ready',latestTradeDate:'2026-09-18'}
  state.applyModelRange()
  assert.equal(state.endDate.value,'2026-09-18')
  assert.deepEqual(state.symbols.value,['512100'])
  assert.equal(state.canSubmit.value,true)
})

for (const algo of ['dqn','sac','ddpg']) {
  test(`${algo} selects its own model, dates, errors and request snapshot`, async t => {
    const scope=effectScope();t.after(()=>scope.stop())
    const items=['ppo','dqn','sac','ddpg'].map(id=>({...ppo(true),id,name:id.toUpperCase(),
      parameterSchema:{type:'object',required:['modelRef'],properties:{modelRef:{type:'string',enum:[`${id}-reviewed`],default:`${id}-reviewed`}}},
      modelContext:{...ppo(true).modelContext,modelRef:`${id}-reviewed`}}))
    let payload
    const jobId='11111111-1111-4111-8111-111111111111'
    const client={createBacktest:async p=>{payload=p;return {jobId,status:'queued'}},getBacktest:async()=>({jobId,status:'succeeded',request:payload})}
    const state=scope.run(()=>useBacktest(ref(items),ref({status:'ready',latestTradeDate:'2026-09-18'}),ref([]),client,null))
    state.strategyId.value='ppo'
    state.strategyId.value=algo
    assert.deepEqual(state.parameters.value,{modelRef:`${algo}-reviewed`})
    assert.ok(state.validationError.value.startsWith(algo.toUpperCase()))
    state.symbols.value=['512100','600519'];state.applyModelRange()
    assert.equal(state.canSubmit.value,true)
    await state.submit()
    assert.equal(payload.strategyId,algo)
    assert.equal(payload.parameters.modelRef,`${algo}-reviewed`)
    assert.deepEqual(payload.symbols,['512100','600519'])
    state.strategyId.value='ppo'
    assert.equal(state.strategyName.value,algo.toUpperCase())
    assert.equal(state.selectedStrategy.value.name,'PPO')
  })
}
