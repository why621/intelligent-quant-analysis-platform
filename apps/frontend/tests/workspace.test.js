import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, ref } from 'vue'
import { useAssetDirectory } from '../src/dashboard/use-asset-directory.js'
import { useWorkspaceNavigation, tabFromHash } from '../src/dashboard/use-workspace-navigation.js'
import { createChartLifecycle } from '../src/dashboard/chart-lifecycle.js'

test('directory search respects filters, explicit global search preserves filters and selections', t => {
  const scope = effectScope(); t.after(() => scope.stop())
  const assets = ref([
    {symbol:'600171', name:'上海贝岭', assetType:'stock', exchange:'SSE'},
    {symbol:'512480', name:'半导体ETF', assetType:'etf', exchange:'SSE'},
    {symbol:'510300', name:'沪深300ETF', assetType:'etf', exchange:'SSE'}
  ])
  const dir = scope.run(() => useAssetDirectory(assets))
  dir.kind.value = 'stock'; dir.categoryId.value = 'semiconductor'; dir.query.value = '半导体'
  assert.deepEqual(dir.matches.value.map(a=>a.symbol), ['600171'])
  dir.searchScope.value = 'all'
  assert.deepEqual(dir.matches.value.map(a=>a.symbol), ['600171','512480'])
  dir.query.value = ''
  assert.equal(dir.kind.value, 'stock'); assert.equal(dir.categoryId.value, 'semiconductor')
  assert.deepEqual(dir.matches.value.map(a=>a.symbol), ['600171'])
  dir.kind.value = 'etf'; assets.value = assets.value.filter(a=>a.symbol!=='512480')
  assert.equal(dir.categoryId.value, null)
  assert.match(dir.notice.value, /已恢复不限行业/)
  dir.resetFilters(); assert.equal(dir.searchScope.value, 'filtered')
  assert.equal(dir.inKind.value.length, 2)
})

test('workspace restores hashes and browser history; invalid tabs cannot become active', () => {
  const listeners = new Map(); const pushed = []
  const target = {location:{hash:'#ranking'}, history:{pushState:(_s,_t,hash)=>{pushed.push(hash);target.location.hash=hash}},
    addEventListener:(n,fn)=>listeners.set(n,fn), removeEventListener:n=>listeners.delete(n)}
  const nav = useWorkspaceNavigation(target); nav.start()
  assert.equal(nav.activeTab.value,'ranking'); assert.equal(nav.select('backtest'),true)
  nav.select('backtest'); assert.deepEqual(pushed,['#backtest'])
  assert.equal(nav.select('missing'),false)
  target.location.hash='#correlation'; listeners.get('popstate')()
  assert.equal(nav.activeTab.value,'correlation')
  assert.equal(tabFromHash('#missing'),'market'); nav.dispose(); assert.equal(listeners.size,0)
})

test('charts load only for a visible panel and preserve legend/zoom across theme recreation', async () => {
  let mode='dark', loads=0, disposed=0; const charts=[]
  const el={clientWidth:0,clientHeight:300}
  const controller=createChartLifecycle({equity:{tab:'backtest',element:{value:el},load:async()=>{loads++;return{}},
    create:()=>({init:()=>{const chart={options:[],setOption(o){this.options.push(o)},getOption:()=>({legend:[{selected:{策略:false}}],dataZoom:[{start:20,end:80}]}),dispose:()=>disposed++,resize:()=>{}};charts.push(chart);return chart}}),option:()=>({series:[{data:[1,2]}]})}}, {theme:()=>mode})
  await controller.sync('market'); await controller.sync('backtest'); assert.equal(loads,0)
  el.clientWidth=600; await controller.sync('backtest'); assert.equal(loads,1)
  mode='light'; await controller.sync('backtest'); assert.equal(charts.length,2);assert.equal(disposed,1)
  assert.deepEqual(charts[1].options[1].legend[0].selected,{策略:false})
  assert.equal(charts[1].options[1].dataZoom[0].start,20)
  controller.dispose(); await controller.sync('backtest'); assert.equal(charts.length,2)
})

test('late chart module cannot initialize after disposal and failed loads can retry', async () => {
  let resolve;let created=0;const errors=[]
  const def={tab:'market',element:{value:{clientWidth:200,clientHeight:200}},load:()=>new Promise(r=>{resolve=r}),create:()=>{created++;return{}},option:()=>({})}
  const controller=createChartLifecycle({chart:def},{theme:()=> 'dark',onError:(_n,e)=>errors.push(e)})
  const pending=controller.sync('market');controller.dispose();resolve({});await pending;assert.equal(created,0)
  let attempts=0
  def.load=async()=>{if(++attempts===1)throw Error('offline');return{}}
  def.create=()=>({init:()=>({setOption(){},resize(){},dispose(){}})})
  const retry=createChartLifecycle({chart:def},{theme:()=> 'dark',onError:(_n,e)=>errors.push(e)})
  await retry.sync('market'); assert.match(errors.at(-1),/重试/)
  await retry.sync('market'); assert.equal(errors.at(-1),'');assert.equal(attempts,2);retry.dispose()
})


test('empty chart theme changes tolerate unregistered ECharts component defaults', async () => {
  let theme='dark', created=0;const errors=[]
  const controller=createChartLifecycle({chart:{tab:'backtest',element:{value:{clientWidth:600,clientHeight:220}},load:async()=>({}),
    create:()=>({init:()=>{created++;return{getOption:()=>({legend:[],dataZoom:{}}),setOption(){},resize(){},dispose(){}}}}),option:()=>({title:{text:'尚无结果'}})}}, {theme:()=>theme,onError:(_n,e)=>errors.push(e)})
  await controller.sync('backtest');theme='light';await controller.sync('backtest')
  assert.equal(created,2);assert.deepEqual(errors,['','']);controller.dispose()
})
