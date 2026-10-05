<template>
  <div class="relative" :class="$attrs.class" @keydown.escape="close">
    <TextInput ref="input" :model-value="q" type="text" :placeholder="placeholder" :size="size"
      role="combobox" aria-autocomplete="list" :aria-expanded="open" aria-controls="member-search-list"
      :aria-activedescendant="open && hits[active] ? `member-opt-${hits[active].id}` : undefined"
      aria-label="Search members"
      @update:model-value="onType" @focus="onFocus" @blur="onBlur"
      @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" @keydown.enter.prevent="go(hits[active])">
      <template #prefix><span aria-hidden="true" class="text-ink-gray-5">⌕</span></template>
      <template #suffix><kbd v-if="!q && showHint" class="hidden md:inline rounded-2 border border-outline-gray-2 px-1 text-xs text-ink-gray-5">/</kbd></template>
    </TextInput>
    <ul v-if="open" id="member-search-list" role="listbox"
      class="absolute left-0 right-0 md:left-auto md:w-[26rem] z-30 mt-1 max-h-80 overflow-auto rounded-lg border border-outline-gray-2 bg-surface-elevation-1 shadow-lg py-1">
      <li v-for="(m, i) in hits" :key="m.id" :id="`member-opt-${m.id}`" role="option" :aria-selected="i === active"
        class="px-3 py-2 cursor-pointer flex items-center gap-3" :class="i === active ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'"
        @mousedown.prevent="go(m)" @mousemove="active = i">
        <div class="min-w-0">
          <div class="text-base text-ink-gray-9 truncate">{{ m.name }}</div>
          <div class="text-xs text-ink-gray-5 whitespace-nowrap">{{ memberTag(m) }} · {{ m.n_buys }} buys</div>
        </div>
        <VerdictBadge v-if="m.verdict_trade !== 'insufficient'" :verdict="m.verdict_trade" size="sm" class="ml-auto shrink-0" />
      </li>
      <li v-if="!hits.length" class="px-3 py-2 text-sm text-ink-gray-5">No member matches “{{ q }}”.</li>
    </ul>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { TextInput } from 'frappe-ui'
import VerdictBadge from './VerdictBadge.vue'
import { getMembers } from '../lib/data'
import { memberTag } from '../lib/format'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  placeholder: { type: String, default: 'Search members…' },
  size: { type: String, default: 'sm' },
  showHint: { type: Boolean, default: true },   // the "/" keyboard shortcut badge
  autofocus: { type: Boolean, default: false },
})
const router = useRouter()
const input = ref(null)
const q = ref('')
const members = ref([])
const open = ref(false)
const active = ref(0)

const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
const hits = computed(() => {
  const n = norm(q.value.trim())
  if (!n) return []
  const scored = members.value
    .map((m) => {
      const name = norm(m.name)
      const words = name.split(/\s+/)
      const score = words.some((w) => w.startsWith(n)) ? 3 : name.includes(n) ? 2 : norm(m.state) === n ? 1 : 0
      return { m, score }
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || b.m.n_trades - a.m.n_trades)
  return scored.slice(0, 8).map((x) => x.m)
})

async function onFocus() {
  if (!members.value.length) { try { members.value = await getMembers() } catch (e) { /* search just stays empty */ } }
  if (q.value) open.value = true
}
function onType(v) { q.value = v; open.value = !!v; active.value = 0 }
function onBlur() { setTimeout(close, 120) }
function close() { open.value = false }
function move(d) { if (hits.value.length) active.value = (active.value + d + hits.value.length) % hits.value.length }
function go(m) {
  if (!m) return
  close(); q.value = ''
  router.push(`/members/${m.id}`)
  input.value?.inputElement?.blur()
}
// "/" focuses the search from anywhere, unless the user is already typing somewhere.
function onKey(e) {
  if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) && !e.ctrlKey && !e.metaKey) {
    e.preventDefault(); input.value?.inputElement?.focus()
  }
}
onMounted(() => { if (props.showHint) window.addEventListener('keydown', onKey); if (props.autofocus) input.value?.inputElement?.focus() })
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
