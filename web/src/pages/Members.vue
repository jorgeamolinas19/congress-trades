<template>
  <div class="space-y-5">
    <div class="max-w-3xl">
      <h1 class="text-2xl font-semibold text-ink-gray-9">Members</h1>
      <p class="mt-2 text-ink-gray-7 leading-relaxed">
        For each member: did the stocks they bought beat the S&amp;P 500 over the next six months (their own
        timing), and could you have profited by copying them once the trade was disclosed? "Significant" means
        the factor-adjusted alpha survives a correction for testing every member at once.
      </p>
    </div>

    <CoverageNote class="max-w-3xl" />

    <div class="flex flex-wrap items-end gap-3">
      <TextInput v-model="q" placeholder="Search member or state…" class="w-full sm:w-64" aria-label="Search members" />
      <Select v-model="chamber" :options="chamberOpts" class="w-36" aria-label="Chamber" />
      <Select v-model="party" :options="partyOpts" class="w-40" aria-label="Party" />
      <TabButtons v-model="view" :options="[{ label: 'Their timing', value: 'trade' }, { label: 'Copying them', value: 'filing' }]" />
      <label class="flex items-center gap-2 text-base text-ink-gray-7">
        <Checkbox v-model="showAll" /> Include members with too few trades
      </label>
    </div>

    <div v-if="error" class="text-ink-red-6">{{ error }}</div>
    <div v-else-if="!members.length" class="text-ink-gray-5">Loading…</div>
    <div v-else class="overflow-x-auto rounded-lg border border-outline-gray-2">
      <table class="w-full text-base">
        <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
          <tr>
            <th v-for="c in cols" :key="c.key" scope="col"
              class="px-3 py-2 font-medium whitespace-nowrap" :class="[c.align === 'right' ? 'text-right' : 'text-left', c.cls]">
              <button v-if="c.sort" class="inline-flex items-center gap-1 hover:text-ink-gray-9" @click="sortBy(c.key)"
                :aria-label="`Sort by ${c.label}`">
                {{ c.label }}<span class="text-ink-gray-4" aria-hidden="true">{{ sortKey === c.key ? (desc ? '↓' : '↑') : '↕' }}</span>
              </button>
              <span v-else>{{ c.label }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in rows" :key="m.id" class="border-t border-outline-gray-1 hover:bg-surface-gray-1">
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
          <tr v-if="!rows.length"><td :colspan="cols.length" class="px-3 py-6 text-center text-ink-gray-5">No members match.</td></tr>
        </tbody>
      </table>
    </div>
    <p class="text-sm text-ink-gray-5 leading-relaxed max-w-3xl">
      <strong>vs SPY</strong>: annualized return of the member's 6-month copycat portfolio minus SPY over the same days.
      <strong>t</strong>: t-statistic of the Fama-French 5 + momentum alpha (|t| &gt; 2 is the usual bar, before correcting for testing many members).
      <strong>Hit rate</strong>: share of purchases that beat SPY over the following six months.
      <strong>Delay</strong>: median days from trade to disclosure.
      Members with fewer than 10 stock purchases or under a year of holdings get no verdict.
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Checkbox, Select, TabButtons, TextInput } from 'frappe-ui'
import VerdictBadge from '../components/VerdictBadge.vue'
import CoverageNote from '../components/CoverageNote.vue'
import { getMembers } from '../lib/data'
import { excessClass, memberTag, pct, signedPct, tstat } from '../lib/format'

const route = useRoute()
const router = useRouter()
const members = ref([])
const error = ref('')
onMounted(async () => { try { members.value = await getMembers() } catch (e) { error.value = e.message } })

// Filters live in the URL so a filtered leaderboard can be shared.
const q = ref(route.query.q || '')
const chamber = ref(route.query.chamber || 'all')
const party = ref(route.query.party || 'all')
const view = ref(route.query.view || 'trade')
const showAll = ref(route.query.all === '1')
const sortKey = ref(route.query.sort || 'excess')
const desc = ref(route.query.dir !== 'asc')
watch([q, chamber, party, view, showAll, sortKey, desc], () => {
  router.replace({ query: {
    ...(q.value && { q: q.value }), ...(chamber.value !== 'all' && { chamber: chamber.value }),
    ...(party.value !== 'all' && { party: party.value }), ...(view.value !== 'trade' && { view: view.value }),
    ...(showAll.value && { all: '1' }), ...(sortKey.value !== 'excess' && { sort: sortKey.value }),
    ...(!desc.value && { dir: 'asc' }),
  } })
})

const chamberOpts = [{ label: 'Both chambers', value: 'all' }, { label: 'House', value: 'House' }, { label: 'Senate', value: 'Senate' }]
const partyOpts = [{ label: 'All parties', value: 'all' }, { label: 'Democrats', value: 'Democrat' },
  { label: 'Republicans', value: 'Republican' }, { label: 'Independents', value: 'Independent' }]

const cols = [
  { key: 'name', label: 'Member', sort: true },
  { key: 'buys', label: 'Buys', sort: true, align: 'right' },
  { key: 'ret', label: 'Return / yr', sort: true, align: 'right', cls: 'hidden md:table-cell' },
  { key: 'excess', label: 'vs SPY / yr', sort: true, align: 'right' },
  { key: 't', label: 'Alpha t', sort: true, align: 'right', cls: 'hidden md:table-cell' },
  { key: 'hit', label: 'Hit rate', sort: true, align: 'right', cls: 'hidden lg:table-cell' },
  { key: 'delay', label: 'Delay', sort: true, align: 'right', cls: 'hidden lg:table-cell' },
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

const rows = computed(() => {
  const needle = q.value.trim().toLowerCase()
  const f = members.value.filter((m) =>
    (showAll.value || m[`verdict_${view.value}`] !== 'insufficient') &&
    (chamber.value === 'all' || m.chamber === chamber.value) &&
    (party.value === 'all' || m.party === party.value) &&
    (!needle || m.name.toLowerCase().includes(needle) || (m.state || '').toLowerCase() === needle))
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
