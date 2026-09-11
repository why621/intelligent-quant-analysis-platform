// Directory identity is not a constituent snapshot or a market-data version.
export async function loadAssetCatalog(client, isCurrent = () => true) {
  const items = []
  const symbols = new Set()
  const identities = new Set()
  let version
  let matchedTotal
  let offset = 0
  const invalid = () => new Error('资产目录不完整或版本不一致，请重新加载；旧后端需先升级')
  for (let pageNumber = 0; pageNumber < 10; pageNumber += 1) {
    if (!isCurrent()) throw new Error('目录加载已被新请求替代')
    const page = await client.listAssets({ limit: 100, offset })
    if (!isCurrent()) throw new Error('目录加载已被新请求替代')
    if (!Array.isArray(page?.items) || page.items.length > 100 ||
        page.total !== page.items.length || page.offset !== offset ||
        !Number.isInteger(page.matchedTotal) || page.matchedTotal < 0 ||
        page.matchedTotal > 1000 || !/^[a-f0-9]{64}$/.test(page.catalogVersion)) throw invalid()
    if (pageNumber === 0) {
      version = page.catalogVersion
      matchedTotal = page.matchedTotal
    }
    if (version !== page.catalogVersion || matchedTotal !== page.matchedTotal) throw invalid()
    for (const asset of page.items) {
      if (!/^[0-9]{6}$/.test(asset?.symbol) ||
          !['stock', 'etf'].includes(asset.assetType) ||
          !['SSE', 'SZSE', 'BSE'].includes(asset.exchange) ||
          asset.assetId !== `${asset.assetType}:${asset.exchange}:${asset.symbol}` ||
          typeof asset.name !== 'string' || !asset.name ||
          typeof asset.active !== 'boolean' ||
          symbols.has(asset.symbol) || identities.has(asset.assetId)) throw invalid()
      symbols.add(asset.symbol)
      identities.add(asset.assetId)
      items.push(asset)
    }
    if (items.length > matchedTotal) throw invalid()
    if (page.nextOffset === null) {
      if (items.length !== matchedTotal) throw invalid()
      return { items, catalogVersion: version }
    }
    if (!page.items.length || items.length >= matchedTotal ||
        page.nextOffset !== offset + page.items.length) throw invalid()
    offset = page.nextOffset
  }
  throw invalid()
}
