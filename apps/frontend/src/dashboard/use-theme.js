import { ref } from 'vue'

// CR077：昼夜主题。深色是 CSS 默认态（html 上不加属性），
// 浅色通过 documentElement 的 data-theme="light" 属性开启，
// 与 index.html 头部的防闪烁预置脚本保持同一判定：存储里只认 'light'。
export const THEME_STORAGE_KEY = 'quant-theme'
export const LIGHT_THEME = 'light'
export const DARK_THEME = 'dark'

// 初始主题：存储值为 'light' 时恢复浅色，其余（缺失 / 'dark' / 损坏数据）一律默认深色。
// storage 可注入（node --test 传假对象）；读取失败按无存储处理。
export function resolveInitialTheme(storage) {
  try {
    if (storage?.getItem(THEME_STORAGE_KEY) === LIGHT_THEME) return LIGHT_THEME
  } catch { /* Storage is optional, including in private browsing. */ }
  return DARK_THEME
}

// 把主题同步到 document：浅色写 data-theme="light"，深色移除属性回到默认态。
// documentRef 可注入（测试传 { documentElement: { dataset: {} } }），缺失时静默跳过。
export function applyTheme(documentRef, theme) {
  const root = documentRef?.documentElement
  if (!root) return
  if (theme === LIGHT_THEME) root.dataset.theme = LIGHT_THEME
  else delete root.dataset.theme
}

// 切换时写回存储；写入失败不阻塞切换（隐私模式下 Storage 可能不可用）。
export function persistTheme(storage, theme) {
  try { storage?.setItem(THEME_STORAGE_KEY, theme) } catch { /* Optional. */ }
}

export function useTheme(deps = {}) {
  let storage = deps.storage
  if (storage === undefined) {
    try { if (typeof globalThis !== 'undefined') storage = globalThis.localStorage } catch { storage = null }
  }
  const documentRef = deps.document !== undefined
    ? deps.document
    : (typeof document !== 'undefined' ? document : null)

  const theme = ref(resolveInitialTheme(storage))
  // 与防闪烁脚本对齐：挂载时按解析结果同步一次属性（幂等，不产生额外闪帧）。
  applyTheme(documentRef, theme.value)

  function toggleTheme() {
    theme.value = theme.value === LIGHT_THEME ? DARK_THEME : LIGHT_THEME
    applyTheme(documentRef, theme.value)
    persistTheme(storage, theme.value)
  }

  return { theme, toggleTheme }
}
