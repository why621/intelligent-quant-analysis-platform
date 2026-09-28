import assert from 'node:assert/strict'
import test from 'node:test'
import { modelWindowLines, strategyDescription } from '../src/dashboard/model-disclosure.js'

test('long model discloses validation as in-sample and reserved test without performance claims', () => {
  const text=modelWindowLines({trainStartDate:'2015-01-05',trainEndDate:'2019-12-31',
    valStartDate:'2020-01-02',valEndDate:'2021-12-31',testStartDate:'2022-01-04',
    testEndDate:'2024-12-31',outOfSampleStartDate:'2022-01-01'}).join(' ')
  assert.match(text,/2020-01-02 至 2021-12-31（属于样本内/)
  assert.match(text,/2022-01-04 至 2024-12-31/)
  assert.match(text,/不代表已通过绩效验收/)
  assert.match(text,/样本外日期下限：2022-01-01/)
})
test('legacy model does not invent validation or test dates', () => {
  const text=modelWindowLines({trainStartDate:'2025-09-09',trainEndDate:'2026-06-30',outOfSampleStartDate:'2026-07-01'}).join(' ')
  assert.match(text,/未记录独立验证区间/)
  assert.match(text,/预留测试区间：此模型未记录/)
  assert.deepEqual(modelWindowLines(null),[])
})
for (const algo of ['PPO','DQN','SAC','DDPG']) test(`${algo} uses its actual algorithm label`, () => {
  const label=strategyDescription({id:algo.toLowerCase(),name:`${algo} 强化学习`,status:'experimental',backtestEnabled:true})
  assert.match(label,new RegExp(algo))
  if(algo !== 'PPO') assert.doesNotMatch(label,/PPO/)
})
test('unavailable experimental strategy does not claim a deployed model', () => {
  assert.equal(strategyDescription({name:'DQN',status:'experimental',backtestEnabled:false}),'暂未开放')
})
