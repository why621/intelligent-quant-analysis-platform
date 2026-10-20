import assert from 'node:assert/strict'
import test from 'node:test'
import { modelScopeLines, modelWindowLines, strategyDescription } from '../src/dashboard/model-disclosure.js'

test('picker distinguishes deployed single-asset and joint models before selection', () => {
  const common = {status:'experimental', backtestEnabled:true}
  assert.match(strategyDescription({...common, modelContext:{symbols:['510300']}}),
    /旧单资产模型.*仅支持 510300.*多资产组合/)
  assert.match(strategyDescription({...common, modelContext:{portfolioMode:'joint_portfolio'}}),
    /2–10只联合决策.*共享资金/)
})

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
for (const algo of ['PPO','DQN','SAC','TD3','DDPG']) test(`${algo} uses its actual algorithm label`, () => {
  const label=strategyDescription({id:algo.toLowerCase(),name:`${algo} 强化学习`,status:'experimental',backtestEnabled:true})
  assert.match(label,new RegExp(algo))
  if(algo !== 'PPO') assert.doesNotMatch(label,/PPO/)
})
test('unavailable experimental strategy does not claim a deployed model', () => {
  assert.equal(strategyDescription({name:'DQN',status:'experimental',backtestEnabled:false}),'暂未开放')
})

test('masked representation discloses training switches without promising web switches or alpha', () => {
  const text = modelScopeLines({portfolioMode:'joint_portfolio',assetScope:'published_universe',
    representationLearning:{method:'earnmore_inspired_masked_features'}}).join(' ')
  assert.match(text, /并非完整复刻/)
  assert.match(text, /固定资产组合/)
  assert.match(text, /尚未证明收益提升/)
})


test('research model discloses folds, scope, unproven performance and fee mismatch', () => {
  const text=modelWindowLines({trainStartDate:'2015-01-05',trainEndDate:'2018-06-30',
    valStartDate:'2018-07-01',valEndDate:'2021-12-31',outOfSampleStartDate:'2022-01-01',
    valFolds:[{start:'2018-07-01',end:'2019-09-30'}],
    trainingConsistency:'research_backfill_unpublished'}).join(' ')
  assert.match(text,/验证折1：2018-07-01 至 2019-09-30/)
  assert.match(text,/未证明超额能力/)
  assert.match(text,/仅开放510300/)
  assert.match(text,/训练与回评口径不同/)
})
