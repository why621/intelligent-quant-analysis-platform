import { computed, ref, watch } from 'vue'
import { ASSET_CATEGORIES, assetCategories, filterAssets } from './asset-filter.js'

export function useAssetDirectory(assets) {
  const query = ref('')
  const kind = ref('all')
  const categoryId = ref(null)
  const searchScope = ref('filtered')
  const notice = ref('')
  const kinds = [{ id: 'all', label: '全部' }, { id: 'stock', label: '股票' }, { id: 'etf', label: 'ETF' }]
  const inKind = computed(() => assets.value.filter(a => kind.value === 'all' || a.assetType === kind.value))
  const kindOptions = computed(() => kinds.map(k => ({ ...k, count: k.id === 'all' ? assets.value.length : assets.value.filter(a => a.assetType === k.id).length })))
  const categoryOptions = computed(() => ASSET_CATEGORIES.map(c => ({ ...c,
    count: inKind.value.filter(a => assetCategories(a).some(t => t.id === c.id)).length
  })).filter(c => c.count))
  watch([kind, categoryOptions], () => {
    if (categoryId.value && !categoryOptions.value.some(c => c.id === categoryId.value)) {
      categoryId.value = null
      notice.value = '原分类在当前资产类型中不可用，已恢复不限行业。'
    }
  }, { flush: 'sync' })
  const allSearch = computed(() => Boolean(query.value.trim()) && searchScope.value === 'all')
  const matches = computed(() => filterAssets(assets.value, {
    query: query.value, kind: allSearch.value ? 'all' : kind.value,
    categories: allSearch.value || !categoryId.value ? [] : [categoryId.value]
  }))
  const currentPath = computed(() => {
    const type = kinds.find(k => k.id === kind.value)?.label || '全部'
    const category = ASSET_CATEGORIES.find(c => c.id === categoryId.value)?.label
    return allSearch.value ? '全部资产 · 搜索结果' : `${type}${category ? ` · ${category}` : ' · 不限行业'}${query.value.trim() ? ' · 搜索结果' : ''}`
  })
  const hasFilter = computed(() => Boolean(query.value.trim() || kind.value !== 'all' || categoryId.value))
  function resetFilters() { query.value = ''; kind.value = 'all'; categoryId.value = null; searchScope.value = 'filtered'; notice.value = '' }
  return { query, kind, categoryId, searchScope, notice, allSearch, kindOptions, categoryOptions, matches, inKind, currentPath, hasFilter, resetFilters }
}
