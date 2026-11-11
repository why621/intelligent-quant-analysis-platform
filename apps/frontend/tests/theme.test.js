import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope } from 'vue'

import { THEME_STORAGE_KEY, applyTheme, persistTheme, resolveInitialTheme, useTheme }
  from '../src/dashboard/use-theme.js'

// 依赖注入：storage/document 均为假对象，不触碰真实 localStorage 与 DOM。
function setup(t, saved = new Map()) {
  const storage = { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value) }
  const documentRef = { documentElement: { dataset: {} } }
  const scope = effectScope()
  t.after(() => scope.stop())
  const state = scope.run(() => useTheme({ storage, document: documentRef }))
  return { ...state, saved, documentRef }
}

test('without a stored value the theme defaults to dark and no attribute is written', t => {
  const { theme, documentRef } = setup(t)
  assert.equal(theme.value, 'dark')
  assert.equal(documentRef.documentElement.dataset.theme, undefined)
})

test('a stored light theme restores light and sets data-theme on mount', t => {
  const { theme, documentRef } = setup(t, new Map([[THEME_STORAGE_KEY, 'light']]))
  assert.equal(theme.value, 'light')
  assert.equal(documentRef.documentElement.dataset.theme, 'light')
})

test('toggling flips the theme, writes back to storage and syncs the attribute', t => {
  const { theme, toggleTheme, saved, documentRef } = setup(t)
  toggleTheme()
  assert.equal(theme.value, 'light')
  assert.equal(saved.get(THEME_STORAGE_KEY), 'light')
  assert.equal(documentRef.documentElement.dataset.theme, 'light')
  toggleTheme()
  assert.equal(theme.value, 'dark')
  assert.equal(saved.get(THEME_STORAGE_KEY), 'dark')
  assert.equal(documentRef.documentElement.dataset.theme, undefined)
})

test('an invalid stored value falls back to dark without throwing', t => {
  const { theme, documentRef } = setup(t, new Map([[THEME_STORAGE_KEY, 'blue']]))
  assert.equal(theme.value, 'dark')
  assert.equal(documentRef.documentElement.dataset.theme, undefined)
})

test('storage and document failures stay contained', () => {
  const broken = {
    getItem: () => { throw Error('denied') },
    setItem: () => { throw Error('denied') },
  }
  assert.equal(resolveInitialTheme(broken), 'dark')
  assert.equal(resolveInitialTheme(null), 'dark')
  assert.doesNotThrow(() => persistTheme(broken, 'light'))
  assert.doesNotThrow(() => persistTheme(null, 'light'))
  assert.doesNotThrow(() => applyTheme(null, 'light'))
})
