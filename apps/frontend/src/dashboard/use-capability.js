import { ref } from 'vue'
import { api } from '../services/api.js'

// Each input/version change invalidates pending responses immediately.
export function useCapability(client = api) {
  const result = ref(null)
  const message = ref('选择资产和区间后检查数据覆盖')
  const busy = ref(false)
  let generation = 0
  let disposed = false
  function invalidate() {
    generation += 1
    result.value = null
    busy.value = false
    message.value = '选择资产和区间后检查数据覆盖'
  }
  async function check(payload, version) {
    invalidate()
    if (disposed || !version) return
    const current = generation
    busy.value = true
    message.value = '正在检查所需数据…'
    try {
      const value = await client.checkDataCapability(payload)
      if (disposed || current !== generation) return
      if (value.dataContext && value.dataContext.dataVersion !== version) {
        message.value = '数据版本已变化，请刷新页面后重试'
        return
      }
      if (!['ready', 'partial', 'unavailable', 'unknown'].includes(value.state)
          || !Array.isArray(value.issues) || typeof value.message !== 'string') {
        throw new Error('预检响应格式异常')
      }
      result.value = value
      message.value = value.message
    } catch (error) {
      if (!disposed && current === generation) {
        message.value = error.code === 'DATA_VERSION_CHANGED'
          ? '数据版本已变化，请刷新页面后重试'
          : '暂未完成预检，可重试；实际提交仍会检查数据'
      }
    } finally {
      if (!disposed && current === generation) busy.value = false
    }
  }
  function dispose() { disposed = true; invalidate() }
  return { result, message, busy, check, invalidate, dispose }
}
