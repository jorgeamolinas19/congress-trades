<template>
  <div class="space-y-5">
    <PageHeader title="Members">
      Did the stocks each member bought beat the S&amp;P 500 over the next six months? And could you have profited by
      copying them once the trade was disclosed? Click any row for the full record.
    </PageHeader>

    <CoverageNote compact class="max-w-3xl" />

    <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 space-y-3">
      <div class="flex flex-wrap items-center gap-3">
        <TabButtons v-model="view" :options="[{ label: 'Their own timing', value: 'trade' }, { label: 'Copying them', value: 'filing' }]" />
        <span class="text-sm text-ink-gray-5">{{ view === 'trade' ? 'Bought the day they traded.' : 'Bought the day after disclosure, as you could.' }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <TextInput v-model="q" placeholder="Name or state (e.g. TX)" class="w-full sm:w-56" aria-label="Filter by name or state" />
        <Select v-model="chamber" :options="chamberOpts" class="w-36" aria-label="Chamber" />
        <Select v-model="party" :options="partyOpts" class="w-40" aria-label="Party" />
        <Select v-model="verdict" :options="verdictOpts" class="w-44" aria-label="Result" />
        <label class="flex items-center gap-2 text-sm text-ink-gray-7"><Checkbox v-model="showAll" /> Include members with too few trades</label>
        <Button v-if="filtersActive" variant="ghost" label="Reset" class="sm:ml-auto" @click="reset" />
      </div>
    </div>

    <ErrorState v-if="error" :message="error" />
    <TableSkeleton v-else-if="!members.length" :rows="10" :cols="6" />
    <template v-else>
      <div class="flex items-baseline justify-between text-sm text-ink-gray-5">
        <span>{{ num(rows.length) }} members · sorted by {{ cols.find((c) => c.key === sortKey)?.label.toLowerCase() }}{{ desc ? '' : ', ascending' }}</span>
        <span class="hidden md:inline">Click a column to sort</span>
      </div>
      <div v-if="rows.length" class="overflow-x-auto rounded-lg border border-outline-gray-2">
        <table class="w-full text-base">
          <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
            <tr>
              <th v-for="c in cols" :key="c.key" scope="col" :title="c.help"
                class="px-3 py-2 font-medium whitespace-nowrap" :class="[c.align === 'right' ? 'text-right' : 'text-left', c.cls]">
                <button v-if="c.sort" class="inline-flex items-center gap-1 hover:text-ink-gray-9" @click="sortBy(c.key)"
                  :aria-label="`Sort by ${c.label}`" :aria-sort="sortKey === c.key ? (desc ? 'descending' : 'ascending') : 'none'">
                  {{ c.label }}<span :class="sortKey === c.key ? 'text-ink-gray-8' : 'text-ink-gray-4'" aria-hidden="true">{{ sortKey === c.key ? (desc ? '↓' : '↑') : '↕' }}</span>
                </button>
                <span v-else>{{ c.label }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in rows" :key="m.id" class="border-t border-outline-gray-1 hover:bg-surface-gray-1 cursor-pointer"
              @click="open(m, $event)">
              <td class="px-3 py-2.5">
                <router-link :to="`/members/${m.id}`" class="font-medium text-ink-gray-9 hover:underline">{{ m.name }}</router-link>
                <div class="text-sm text-ink-gray-5">{{ memberTag(m) }}</div>
              </td>
              <td class="px-3 py-2.5 text-right num">{{ m.n_buys }}</td>
              <td class="px-3 py-2.5 text-right num hidden md:table-cell">{{ pct(m[view].ann_return) }}</td>
              <td class="px-3 py-2.5 text-right num font-medium" :class="excessClass(m[view].excess_ann)">{{ signedPct(m[view].excess_ann) }}</td>
              <td class="px-3 py-2.5 text-right num hidden md:table-cell">{{ tstat(m[view].alpha_t) }}</td>
              <td class="px-3 py-2.5 text-right num hidden lg:table-cell">{{ pct(m.hit_rate, 0) }}</td>
              <td class="px-3 py-2.5 text-right num hidden lg:table-cell">{{ m.median_delay_days }}d</td>
              <td class="px-3 py-2.5"><VerdictBadge :verdict="m[`verdict_${view}`]" size="sm" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else title="No members match these filters" hint="Try a different name, or include members with too few trades.">
        <Button label="Reset filters" @click="reset" />
      </EmptyState>
    </template>

    <details class="text-sm text-ink-gray-5 max-w-3xl">
      <summary class="cursor-pointer text-ink-gray-7">How to read the columns</summary>
      <dl class="mt-2 grid sm:grid-cols-[8rem_1fr] gap-x-4 gap-y-1">
        <dt class="font-medium text-ink-gray-7">vs SPY / yr</dt><dd>Annualized return of the member's 6-month copycat portfolio minus SPY over the same days.</dd>
        <dt class="font-medium text-ink-gray-7">Alpha t</dt><dd>t-statistic of the Fama-French 5 + momentum alpha. |t| &gt; 2 is the usual bar, before correcting for testing many members.</dd>
        <dt class="font-medium text-ink-gray-7">Hit rate</dt><dd>Share of purchases that beat SPY over the following six months.</dd>
        <dt class="font-medium text-ink-gray-7">Delay</dt><dd>Median days from trade to disclosure. The legal limit is 45.</dd>
        <dt class="font-medium text-ink-gray-7">Verdict</dt><dd>"Significant" means the alpha survives a correction for testing every member at once. Members with fewer than 10 stock purchases or under a year of holdings get no verdict.</dd>
      </dl>
    </details>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Checkbox, Select, TabButtons, TextInput } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'
import VerdictBadge from '../components/VerdictBadge.vue'
import CoverageNote from '../components/CoverageNote.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import { getMembers } from '../lib/data'
import { excessClass, memberTag, num, pct, signedPct, tstat } from '../lib/format'

const route = useRoute()
const router = useRouter()
const members = ref([])
const error = ref('')
onMounted(async () => { try { members.value = await getMembers() } catch (e) { error.value = e.message } })

// Filters live in the URL so a filtered leaderboard can be shared.
const q = ref(route.query.q || '')
const chamber = ref(route.query.chamber || 'all')
const party = ref(route.query.party || 'all')
const verdict = ref(route.query.verdict || 'all')
const view = ref(route.query.view || 'trade')
const showAll = ref(route.query.all === '1')
const sortKey = ref(route.query.sort || 'excess')
const desc = ref(route.query.dir !== 'asc')
watch([q, chamber, party, verdict, view, showAll, sortKey, desc], () => {
  router.replace({ query: {
    ...(q.value && { q: q.value }), ...(chamber.value !== 'all' && { chamber: chamber.value }),
    ...(party.value !== 'all' && { party: party.value }), ...(verdict.value !== 'all' && { verdict: verdict.value }),
    ...(view.value !== 'trade' && { view: view.value }), ...(showAll.value && { all: '1' }),
    ...(sortKey.value !== 'excess' && { sort: sortKey.value }), ...(!desc.value && { dir: 'asc' }),
  } })
})
const filtersActive = computed(() => q.value || chamber.value !== 'all' || party.value !== 'all' || verdict.value !== 'all' || showAll.value)
function reset() { q.value = ''; chamber.value = 'all'; party.value = 'all'; verdict.value = 'all'; showAll.value = false }

const chamberOpts = [{ label: 'Both chambers', value: 'all' }, { label: 'House', value: 'House' }, { label: 'Senate', value: 'Senate' }]
const partyOpts = [{ label: 'All parties', value: 'all' }, { label: 'Democrats', value: 'Democrat' },
  { label: 'Republicans', value: 'Republican' }, { label: 'Independents', value: 'Independent' }]
const verdictOpts = [{ label: 'Any result', value: 'all' }, { label: 'Beat SPY', value: 'beat' }, { label: 'Trailed SPY', value: 'lagged' }]

const cols = [
  { key: 'name', label: 'Member', sort: true },
  { key: 'buys', label: 'Buys', sort: true, align: 'right', help: 'Stock purchases in the data' },
  { key: 'ret', label: 'Return / yr', sort: true, align: 'right', cls: 'hidden md:table-cell', help: 'Annualized return of the 6-month copycat portfolio' },
  { key: 'excess', label: 'vs SPY / yr', sort: true, align: 'right', help: 'Return minus SPY over the same days' },
  { key: 't', label: 'Alpha t', sort: true, align: 'right', cls: 'hidden md:table-cell', help: 't-statistic of the factor-adjusted alpha' },
  { key: 'hit', label: 'Hit rate', sort: true, align: 'right', cls: 'hidden lg:table-cell', help: 'Share of purchases that beat SPY over 6 months' },
  { key: 'delay', label: 'Delay', sort: true, align: 'right', cls: 'hidden lg:table-cell', help: 'Median days from trade to disclosure' },
  { key: 'verdict', label: 'Verdict' },
]
const sortVal = {
  name: (m) => m.name, buys: (m) => m.n_buys, ret: (m) => m[view.value].ann_return,
  excess: (m) => m[view.value].excess_ann, t: (m) => m[view.value].alpha_t, hit: (m) => m.hit_rate,
  delay: (m) => m.median_delay_days,
}
function sortBy(k) {
  if (sortKey.value === k) desc.value = !desc.value
  else { sortKey.value = k; desc.value = k !== 'name' }
}
// Whole row navigates; the name stays a real link for keyboard users and new tabs.
function open(m, e) {
  if (e.target.closest('a')) return
  router.push(`/members/${m.id}`)
}

const rows = computed(() => {
  const needle = q.value.trim().toLowerCase()
  const f = members.value.filter((m) => {
    const v = m[`verdict_${view.value}`]
    return (showAll.value || v !== 'insufficient') &&
      (verdict.value === 'all' || v.startsWith(verdict.value)) &&
      (chamber.value === 'all' || m.chamber === chamber.value) &&
      (party.value === 'all' || m.party === party.value) &&
      (!needle || m.name.toLowerCase().includes(needle) || (m.state || '').toLowerCase() === needle)
  })
  const get = sortVal[sortKey.value]
  const dir = desc.value ? -1 : 1
  // Missing values always sink to the bottom, whichever way the column sorts.
  return [...f].sort((a, b) => {
    const x = get(a), y = get(b)
    if (x === null || x === undefined) return 1
    if (y === null || y === undefined) return -1
    return (x < y ? -1 : x > y ? 1 : 0) * dir
  })
})
</script>
