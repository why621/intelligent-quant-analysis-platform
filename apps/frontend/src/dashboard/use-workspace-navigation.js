import { ref } from 'vue'
export const WORKSPACE_TABS = [
  { id: 'market', label: '市场概况' }, { id: 'correlation', label: '资产相关性' },
  { id: 'backtest', label: '策略回测' }, { id: 'ranking', label: '策略排行' },
  { id: 'allocation', label: '次日配置' }
]
export function tabFromHash(hash) {
  const id = String(hash || '').replace(/^#/, '')
  return WORKSPACE_TABS.some(t => t.id === id) ? id : 'market'
}
export function useWorkspaceNavigation(target = typeof window === 'undefined' ? null : window) {
  const activeTab = ref(tabFromHash(target?.location.hash))
  const restore = () => { activeTab.value = tabFromHash(target?.location.hash) }
  function select(id) {
    if (!WORKSPACE_TABS.some(t => t.id === id)) return false
    activeTab.value = id
    if (target && target.location.hash !== `#${id}`) target.history.pushState(null, '', `#${id}`)
    return true
  }
  function start() { target?.addEventListener('popstate', restore); target?.addEventListener('hashchange', restore) }
  function dispose() { target?.removeEventListener('popstate', restore); target?.removeEventListener('hashchange', restore) }
  return { activeTab, select, start, dispose }
}
