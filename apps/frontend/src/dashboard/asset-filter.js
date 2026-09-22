import { ASSET_CATEGORIES } from './asset-categories.data.js'

export { ASSET_CATEGORIES }
const memberships = new Map()
for (const category of ASSET_CATEGORIES) {
  for (const identity of category.members) {
    const list = memberships.get(identity) || []
    list.push(category)
    memberships.set(identity, list)
  }
}
const normalize = value => String(value ?? '').normalize('NFKC').toLowerCase().trim()

export function assetCategories(asset) {
  if (asset.assetType === 'stock') {
    const identity = `stock:${asset.exchange}:${asset.symbol}`
    if (asset.assetId && asset.assetId !== identity) return []
    return memberships.get(identity) || []
  }
  if (asset.assetType === 'etf') {
    const name = normalize(asset.name)
    return ASSET_CATEGORIES.filter(category => category.etfKeywords.some(word => name.includes(normalize(word))))
  }
  return []
}

export function filterAssets(assets, { kind = 'all', query = '', categories = [] } = {}) {
  const terms = normalize(query).split(/\s+/).filter(Boolean)
  return assets.filter(asset => {
    if (kind !== 'all' && asset.assetType !== kind) return false
    const tags = assetCategories(asset)
    if (categories.length && !tags.some(tag => categories.includes(tag.id))) return false
    const text = normalize([asset.symbol, asset.name, ...tags.flatMap(tag => [tag.label, ...tag.aliases])].join(' '))
    return terms.every(term => text.includes(term))
  })
}
