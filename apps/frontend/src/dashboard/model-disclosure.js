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
