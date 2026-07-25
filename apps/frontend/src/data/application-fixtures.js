// 这些数据只用于后端接口尚未完成时展示布局，页面必须标注“演示数据”。
// 禁止把本文件中的数值用于项目报告、策略排行或投资判断。

export const fallbackAssets = [
  { symbol: '510300', name: '沪深300ETF', assetType: 'etf', exchange: 'SSE', active: true },
  { symbol: '510500', name: '中证500ETF', assetType: 'etf', exchange: 'SSE', active: true },
  { symbol: '159915', name: '创业板ETF', assetType: 'etf', exchange: 'SZSE', active: true },
  { symbol: '512100', name: '中证1000ETF', assetType: 'etf', exchange: 'SSE', active: true },
  { symbol: '600519', name: '贵州茅台', assetType: 'stock', exchange: 'SSE', active: true },
  { symbol: '000858', name: '五粮液', assetType: 'stock', exchange: 'SZSE', active: true },
  { symbol: '600036', name: '招商银行', assetType: 'stock', exchange: 'SSE', active: true },
  { symbol: '000333', name: '美的集团', assetType: 'stock', exchange: 'SZSE', active: true }
]

export const fallbackStrategies = [
  {
    id: 'ma_cross',
    name: '均线交叉',
    category: 'traditional',
    status: 'available',
    description: '短期均线与长期均线的交叉信号。',
    parameterSchema: {}
  },
  {
    id: 'momentum_reversal',
    name: '动量反转',
    category: 'traditional',
    status: 'available',
    description: '根据动量强弱识别趋势和反转。',
    parameterSchema: {}
  },
  {
    id: 'dqn',
    name: 'DQN 强化学习',
    category: 'ai',
    status: 'planned',
    description: '申请书第二阶段规划，尚未进入真实排行。',
    parameterSchema: {}
  },
  {
    id: 'ppo',
    name: 'PPO 强化学习',
    category: 'ai',
    status: 'planned',
    description: '申请书第二阶段规划，尚未进入真实排行。',
    parameterSchema: {}
  },
  {
    id: 'multi_agent',
    name: '多智能体策略',
    category: 'ai',
    status: 'planned',
    description: '申请书第三阶段规划，尚未实现。',
    parameterSchema: {}
  }
]

export const fallbackMarket = {
  tradeDate: null,
  advancing: null,
  declining: null,
  unchanged: null,
  limitUp: null,
  limitDown: null,
  turnoverCny: null,
  northboundNetCny: null,
  indices: [
    { symbol: '000001', name: '上证指数', close: null, changePct: null },
    { symbol: '399001', name: '深证成指', close: null, changePct: null },
    { symbol: '399006', name: '创业板指', close: null, changePct: null },
    { symbol: '000300', name: '沪深300', close: null, changePct: null }
  ]
}
