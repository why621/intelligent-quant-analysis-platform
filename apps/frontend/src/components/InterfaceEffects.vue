<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const motion = ref(true)
const cursor = ref(true)
const reduced = ref(false)
const pointerAvailable = ref(false)
const ring = ref(null)
const motionOn = computed(() => motion.value && !reduced.value)
const cursorOn = computed(() => cursor.value && pointerAvailable.value && !reduced.value)
let cleanup = () => {}

onMounted(() => {
  const root = document.documentElement
  try {
    const saved = JSON.parse(localStorage.getItem('quant-interface') || '{}')
    motion.value = saved.motion !== false
    cursor.value = saved.cursor !== false
  } catch { /* Storage is optional, including in private browsing. */ }
  const reduce = matchMedia('(prefers-reduced-motion: reduce)')
  const fine = matchMedia('(hover: hover) and (pointer: fine)')
  const contrast = matchMedia('(forced-colors: active)')
  let frame = 0
  let point = null
  let pressAnimation
  const reveals = new Set()
  const hide = () => {
    point = null
    root.dataset.quantCursor = 'off'
    ring.value?.classList.remove('is-visible')
    cancelAnimationFrame(frame)
    frame = 0
  }
  const syncMedia = () => {
    reduced.value = reduce.matches
    pointerAvailable.value = fine.matches && !contrast.matches
    hide()
  }
  syncMedia()
  const stop = watch([motionOn, cursorOn], () => {
    root.dataset.quantMotion = motionOn.value ? 'on' : 'off'
    if (!motionOn.value) {
      pressAnimation?.cancel()
      reveals.forEach(animation => animation.cancel())
      reveals.clear()
    }
    hide()
  }, { immediate: true })
  const persist = watch([motion, cursor], () => {
    try { localStorage.setItem('quant-interface', JSON.stringify({ motion: motion.value, cursor: cursor.value })) } catch { /* Optional. */ }
  })
  const render = () => {
    frame = 0
    if (!point || !cursorOn.value) return hide()
    const { x, y } = point
    const target = document.elementFromPoint(x, y)
    if (!target || target.closest('input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable=true], iframe')) return hide()
    const interactive = target.closest('a, button, label, summary, [role=button]')
    const disabled = interactive?.matches(':disabled, [aria-disabled=true]') || interactive?.closest('fieldset:disabled')
    ring.value.style.transform = `translate3d(${x}px, ${y}px, 0)`
    ring.value.classList.add('is-visible')
    ring.value.classList.toggle('is-interactive', !!interactive && !disabled)
    ring.value.classList.toggle('is-disabled', !!disabled)
    root.dataset.quantCursor = 'on'
  }
  const move = event => {
    if (event.pointerType !== 'mouse' || !cursorOn.value) return hide()
    point = { x: event.clientX, y: event.clientY }
    if (!frame) frame = requestAnimationFrame(render)
  }
  const press = event => {
    if (!motionOn.value || root.dataset.quantCursor !== 'on' || event.button !== 0) return
    if (ring.value.classList.contains('is-disabled')) return
    pressAnimation?.cancel()
    pressAnimation = ring.value.firstElementChild.animate([
      { transform: 'scale(1)' }, { transform: 'scale(.65)', offset: .35 }, { transform: 'scale(1)' },
    ], { duration: 240, easing: 'ease-out' })
  }
  const leave = event => { if (!event.relatedTarget) hide() }
  const key = event => { if (event.key === 'Tab' || event.key === 'Escape') hide() }
  const visibility = () => { if (document.hidden) hide() }
  const scroll = () => { if (point && !frame) frame = requestAnimationFrame(render) }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      if (motionOn.value) {
        const animation = entry.target.animate([
        { opacity: .6, transform: 'translateY(12px)' }, { opacity: 1, transform: 'translateY(0)' },
      ], { duration: 420, easing: 'cubic-bezier(.22,1,.36,1)' })
        reveals.add(animation)
        animation.onfinish = () => reveals.delete(animation)
      }
      observer.unobserve(entry.target)
    }
  }, { threshold: .06 })
  document.querySelectorAll('.panel').forEach(panel => observer.observe(panel))
  const events = [
    [window, 'pointermove', move], [window, 'pointerdown', press],
    [window, 'pointerout', leave], [window, 'blur', hide],
    [window, 'keydown', key], [document, 'visibilitychange', visibility],
    [document, 'scroll', scroll],
  ]
  for (const [target, name, listener] of events) target.addEventListener(name, listener, { passive: true, capture: true })
  for (const media of [reduce, fine, contrast]) media.addEventListener('change', syncMedia)
  cleanup = () => {
    hide(); stop(); persist(); observer.disconnect(); pressAnimation?.cancel()
    reveals.forEach(animation => animation.cancel())
    for (const [target, name, listener] of events) target.removeEventListener(name, listener, true)
    for (const media of [reduce, fine, contrast]) media.removeEventListener('change', syncMedia)
    delete root.dataset.quantMotion
    delete root.dataset.quantCursor
  }
})
onBeforeUnmount(() => cleanup())
</script>

<template>
  <div class="interface-controls" aria-label="界面效果设置">
    <span class="interface-caption" aria-hidden="true">DISPLAY /</span>
    <button type="button" :aria-pressed="motionOn" :disabled="reduced" @click="motion = !motion">
      <span class="effect-indicator" aria-hidden="true"></span>{{ reduced ? '系统静态模式' : motionOn ? '动态效果 开' : '动态效果 关' }}
    </button>
    <button v-if="pointerAvailable && !reduced" type="button" :aria-pressed="cursorOn" @click="cursor = !cursor">圆环光标 {{ cursorOn ? '开' : '关' }}</button>
  </div>
  <Teleport to="body"><div ref="ring" class="quant-cursor" aria-hidden="true"><span></span><i></i></div></Teleport>
</template>
