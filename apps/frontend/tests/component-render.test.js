import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('asset directory renders empty, failed and populated catalogs without template errors', async t => {
  const server=await createServer({server:{middlewareMode:true},appType:'custom'})
  t.after(()=>server.close())
  const {default:AssetPicker}=await server.ssrLoadModule('/src/components/AssetPicker.vue')
  for (const [props,expected] of [
    [{modelValue:[],assets:[],loading:true},'正在加载资产目录'],
    [{modelValue:['510300'],assets:[],error:'offline'},'资产目录加载失败'],
    [{modelValue:['512480'],assets:[{symbol:'512480',name:'半导体ETF',assetType:'etf',exchange:'SSE',active:true}]},'半导体ETF']
  ]) {
    const app=createSSRApp(AssetPicker,props)
    app.config.warnHandler=message=>{throw Error(message)}
    const html=await renderToString(app)
    assert.ok(html.includes(expected));assert.ok(html.includes('当前筛选'))
  }
})
