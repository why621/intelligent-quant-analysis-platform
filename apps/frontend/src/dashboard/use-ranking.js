import { computed, getCurrentScope, onScopeDispose, ref, watch } from 'vue'
import { api } from '../services/api.js'
import { displayError } from './common.js'
import { snapshotKey } from './use-research-context.js'

// Rankings follow the draft, but computing is always an explicit user action.
// A publication/model/configuration change invalidates in-flight responses too.
export function useRanking(backtest, dataStatus, strategies, client = api) {
  const result = ref(null)
  const busy = ref(false)
  const error = ref('')
  const notice = ref('')
  const resultKey = ref('')
  let generation = 0
  let disposed = false
  const draft = computed(() => backtest.draft.value)
  const key = computed(() => snapshotKey({ request: draft.value,
    dataVersion: dataStatus.value.dataContext?.dataVersion || null,
    strategies: strategies.value }))
  const stale = computed(() => Boolean(result.value && resultKey.value !== key.value))
  const validationError = computed(() => {
    if (backtest.validationError.value) return backtest.validationError.value
    const days = (Date.parse(draft.value.endDate) - Date.parse(draft.value.startDate)) / 86400000
    return days > 366 ? '排行榜比较区间最多 366 天，请在回测配置中缩短日期区间。' : ''
  })
  const canSubmit = computed(() => !disposed && !busy.value && !validationError.value)
  watch(key, () => {
    generation += 1
    error.value = ''
    if (busy.value) notice.value = '配置已变化；正在返回的旧配置结果将被忽略，请完成后按当前配置重新计算。'
  }, { flush: 'sync' })
  const submit = async () => {
    if (disposed || busy.value) return
    if (validationError.value) { error.value = validationError.value; return }
    const token = ++generation
    const submittedKey = key.value
    const payload = JSON.parse(JSON.stringify(draft.value))
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      const response = await client.calculateStrategyRanking(payload)
      if (disposed || token !== generation || submittedKey !== key.value) return
      if (!Array.isArray(response?.items) || !response.request || !Array.isArray(response.unavailableStrategies)) {
        throw Error('排行榜响应缺少配置快照或排除记录，请核对前后端版本。')
      }
      if (snapshotKey(response.request) !== snapshotKey(payload)) {
        throw Error('返回的排行配置与本次提交不一致，未展示该结果，请重新计算。')
      }
      const version = dataStatus.value.dataContext?.dataVersion
      if (version && response.dataContext?.dataVersion !== version) {
        throw Error('排行数据批次与当前研究批次不一致，请刷新数据后重新计算。')
      }
      result.value = response
      resultKey.value = submittedKey
    } catch (requestError) {
      if (!disposed && token === generation) error.value = displayError(requestError)
    } finally {
      if (!disposed) busy.value = false
    }
  }
  if (getCurrentScope()) onScopeDispose(() => { disposed = true; generation += 1 })
  return { result, busy, error, notice, draft, stale, validationError, canSubmit, submit,
    items: computed(() => result.value?.items || []),
    unavailable: computed(() => result.value?.unavailableStrategies || []) }
}
