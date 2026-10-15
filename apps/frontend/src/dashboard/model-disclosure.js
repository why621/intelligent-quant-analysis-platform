// Keep selected-model and historical-result disclosure consistent.
export function modelWindowLines(model) {
  if (!model) return []
  return [
    ...(model.valFolds || []).map((f, i) => `验证折${i + 1}：${f.start} 至 ${f.end}（用于选优，属于样本内）。`),
    ...(model.trainingConsistency === 'research_backfill_unpublished' ? [
      '来源：独立研究回填模型；未证明超额能力或跨资产通用性，本批仅开放510300。',
      '费用口径：训练奖励使用佣金0.03%、卖出印花税0.05%、滑点0.02%；网页ETF回评使用佣金0.03%、印花税0%、滑点0.02%。训练与回评口径不同，结果仅供实验。'
    ] : []),
    `训练区间：${model.trainStartDate} 至 ${model.trainEndDate}。`,
    model.valStartDate && model.valEndDate
      ? `验证区间：${model.valStartDate} 至 ${model.valEndDate}（属于样本内，不用于样本外回测）。`
      : '验证区间：此模型未记录独立验证区间。',
    model.testStartDate && model.testEndDate
      ? `预留测试区间：${model.testStartDate} 至 ${model.testEndDate}（模型记录，不代表已通过绩效验收或网页可用行情范围）。`
      : '预留测试区间：此模型未记录。',
    `样本外日期下限：${model.outOfSampleStartDate}；实际回测还需满足已发布行情范围和预热要求。`
  ]
}

export function strategyDescription(strategy) {
  if (strategy.status !== 'available') return strategy.status === 'experimental' && strategy.backtestEnabled
    ? `实验性回测 · 已部署 ${strategy.name}模型` : '暂未开放'
  return ({ ma_cross: '短长均线交叉，观察趋势变化。',
    momentum_reversal: '依据近期动量与反转条件生成信号。' })[strategy.id] || '选择后查看可用参数。'
}

export function modelAssetError(model, symbols, assets = []) {
  if (!model || model.portfolioMode !== 'joint_portfolio') return ''
  if (symbols.length < 2 || symbols.length > 10) return '组合模型请选择 2–10 只不同资产。'
  if (model.assetScope === 'published_universe') {
    if (!assets.length) return '请等待完整的发布资产目录加载后使用全资产组合模型。'
    const available = new Set(assets.filter(asset => asset.active && ['stock', 'etf'].includes(asset.assetType)).map(asset => asset.symbol))
    if (symbols.some(symbol => !available.has(symbol))) return '组合模型仅支持当前发布目录中的股票和 ETF，请重新选择资产。'
    return ''
  }
  if (symbols.some(symbol => !(model.symbols || []).includes(symbol))) return `该旧组合模型仅支持训练池内资产：${(model.symbols || []).join('、')}。`
  return ''
}

export function modelScopeLines(model) {
  if (!model) return []
  if (model.portfolioMode === 'joint_portfolio') return [
    model.assetScope === 'published_universe'
      ? '适用范围：当前发布目录中的股票和 ETF，任选 2–10 只联合输入、输出资产与现金权重，共享同一资金账户。'
      : `适用范围：此版本仅支持训练池内 2–10 只资产（${(model.symbols || []).join('、')}）。`,
    '实际可运行区间仍需满足真实历史、样本外日期及预热要求；已核实停牌仅沿用估值且不成交，未知缺口会明确拒绝。',
    '资产适用范围与训练样本不同；支持选择不等于证明所有资产组合均有超额收益。',
    ...(model.costPolicy === 'request_configurable' ? ['费用与预留现金使用当前研究配置；训练时成本见模型记录，改变执行成本不意味着重新训练。'] : ['此旧版本使用记录的固定成本，额外预留现金须为 0%。']),
    ...(model.crossAssetValidationStatus === 'execution_validated' ? ['跨资产验证：已验证联合执行及账本一致性；这不是收益有效性认证。'] : [])
  ]
  return [model.assetScope === 'published_universe'
    ? '该旧单资产模型逐资产独立推理、等分资金后合并净值；不是联合组合模型。'
    : `当前模型仅支持 ${(model.symbols || []).join('、')}。`]
}
