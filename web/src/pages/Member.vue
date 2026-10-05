<template>
  <div v-if="error" class="max-w-xl space-y-4">
    <ErrorState :message="error" />
    <div>
      <div class="text-sm text-ink-gray-6 mb-1">Looking for someone else?</div>
      <MemberSearch class="max-w-sm" size="md" :show-hint="false" autofocus />
    </div>
  </div>

  <div v-else-if="!m" class="space-y-6" aria-busy="true">
    <div class="space-y-2"><Skeleton class="h-3 w-40 rounded-2" /><Skeleton class="h-8 w-72 rounded-2" /><Skeleton class="h-4 w-96 rounded-2" /></div>
    <div class="grid md:grid-cols-2 gap-3"><Skeleton class="h-44 rounded-lg" /><Skeleton class="h-44 rounded-lg" /></div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3"><Skeleton v-for="i in 4" :key="i" class="h-24 rounded-lg" /></div>
    <TableSkeleton :rows="6" />
  </div>

  <div v-else class="space-y-8">
    <PageHeader :title="m.name" :crumbs="[{ label: 'Members', route: '/members' }, { label: m.name }]">
      {{ m.party || 'Unknown party' }} · {{ m.chamber }}<span v-if="m.state"> · {{ m.state }}</span>
      · {{ num(m.n_trades) }} stock trades<span v-if="m.n_other">, {{ num(m.n_other) }} options, bonds &amp; other</span>
      · {{ date(m.first_trade) }} to {{ date(m.last_trade) }}
      <template #actions>
        <Button variant="outline" :label="copied ? 'Link copied' : 'Share'" @click="share" />
      </template>
    </PageHeader>

    <!-- Section jump links: sticky on wider screens, where the header is one row tall. -->
    <nav class="md:sticky md:top-14 z-10 -mx-4 px-4 py-2 bg-surface-base/95 backdrop-blur border-b border-outline-gray-2 flex gap-1 overflow-x-auto" aria-label="On this page">
      <a v-for="s in sections" :key="s.id" :href="`#${s.id}`" class="px-2.5 py-1 rounded-2 text-sm text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 whitespace-nowrap">{{ s.label }}</a>
    </nav>

    <section id="summary" class="scroll-mt-28 space-y-3">
      <div class="grid md:grid-cols-2 gap-3">
        <div v-for="v in views" :key="v.key" class="rounded-lg border border-outline-gray-2 p-4">
          <div class="text-sm text-ink-gray-5">{{ v.question }}</div>
          <div class="mt-2"><VerdictBadge :verdict="m[`verdict_${v.key}`]" /></div>
          <template v-if="m[v.key].excess_ann !== undefined && m[v.key].excess_ann !== null">
            <div class="mt-3 text-2xl font-semibold num" :class="excessClass(m[v.key].excess_ann)">
              {{ signedPct(m[v.key].excess_ann) }} <span class="text-base font-normal text-ink-gray-6">a year vs SPY</span>
            </div>
            <div class="mt-1 text-sm text-ink-gray-6 num">
              {{ pct(m[v.key].ann_return) }} vs {{ pct(m[v.key].spy_ann_return) }} for SPY over the same {{ num(m[v.key].invested_days) }} trading days.
              <template v-if="m[v.key].alpha_t !== undefined">
                Factor-adjusted alpha {{ signedPct(m[v.key].alpha_ann) }} (t = {{ tstat(m[v.key].alpha_t) }}, beta {{ m[v.key].beta }}).
              </template>
            </div>
          </template>
          <p v-else class="mt-3 text-sm text-ink-gray-6">
            {{ m.n_buys ? 'Fewer than 10 stock purchases, or under a year of holdings: too little to judge.' : 'No stock purchases in the data; see the options, bonds and funds section below.' }}
          </p>
          <p class="mt-2 text-sm text-ink-gray-5">{{ v.explain }}</p>
        </div>
      </div>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Stock purchases" :value="num(m.n_buys)" :sub="`${num(m.n_sells)} sales`" />
        <StatTile label="Hit rate" :value="pct(m.hit_rate, 0)" sub="Purchases that beat SPY over 6 months" />
        <StatTile label="Median disclosure delay" :value="`${m.median_delay_days} days`" :sub="`${pct(m.pct_late, 0)} filed after 45 days`" />
        <StatTile label="Disclosed volume" :value="money(m.volume_mid)" sub="Sum of range midpoints" />
      </div>
      <CoverageNote compact />
    </section>

    <section id="calculator" class="scroll-mt-28">
      <CopyCalculator v-if="odds" :member="m" :odds="odds" />
    </section>

    <section id="performance" class="scroll-mt-28 space-y-4">
      <div v-if="m.series && m.series.dates && m.series.dates.length > 4" class="rounded-lg border border-outline-gray-2 p-4">
        <GrowthChart title="Growth of $1 while invested" subtitle="Their purchases at their own timing, held 6 months, vs SPY over the same days. Flat stretches are periods with no open positions."
          :dates="m.series.dates" :series="[
            { label: 'Their purchases', color: 'trade', values: m.series.member },
            { label: 'SPY', color: 'spy', values: m.series.spy },
          ]" />
      </div>
      <div v-if="m.top_buys.length">
        <h2 class="text-lg font-semibold text-ink-gray-9">Most-bought stocks</h2>
        <div class="mt-2 flex flex-wrap gap-2">
          <button v-for="t in m.top_buys" :key="t.ticker" class="rounded-full border border-outline-gray-2 px-3 py-1 text-sm hover:bg-surface-gray-2"
            :title="`Filter the trades below to ${t.ticker}`" @click="ticker = t.ticker; scrollTo('stocks')">
            <span class="font-medium">{{ t.ticker }}</span> <span class="text-ink-gray-5">× {{ t.n }}</span>
          </button>
        </div>
      </div>
    </section>

    <section id="stocks" class="scroll-mt-28" v-if="m.trades.length">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-semibold text-ink-gray-9">Stock trades</h2>
        <TabButtons v-model="side" :options="[{ label: 'All', value: 'all' }, { label: 'Buys', value: 'buy' }, { label: 'Sells', value: 'sell' }]" />
        <TextInput v-model="ticker" placeholder="Filter ticker…" class="w-36" aria-label="Filter by ticker" />
        <Button v-if="ticker || side !== 'all'" variant="ghost" label="Clear" @click="ticker = ''; side = 'all'" />
        <span class="text-sm text-ink-gray-5 ml-auto">{{ num(filtered.length) }} trades</span>
      </div>
      <div v-if="filtered.length" class="mt-3 overflow-x-auto rounded-lg border border-outline-gray-2">
        <table class="w-full text-base">
          <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
            <tr>
              <th class="px-3 py-2 text-left font-medium">Traded</th>
              <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Disclosed</th>
              <th class="px-3 py-2 text-left font-medium">Stock</th>
              <th class="px-3 py-2 text-left font-medium">Type</th>
              <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Amount</th>
              <th class="px-3 py-2 text-right font-medium" title="Stock return over the 6 months after the trade, minus SPY">6 mo vs SPY</th>
              <th class="px-3 py-2 text-right font-medium hidden md:table-cell" title="Based on your risk settings in the calculator above">Max to put in</th>
              <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">Filing</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(t, i) in page" :key="i" class="border-t border-outline-gray-1 hover:bg-surface-gray-1">
              <td class="px-3 py-2 whitespace-nowrap num">{{ date(t.tx_date) }}</td>
              <td class="px-3 py-2 whitespace-nowrap num hidden md:table-cell">
                {{ date(t.filing_date) }}
                <span class="text-sm" :class="t.delay_days > 45 ? 'text-ink-amber-7' : 'text-ink-gray-5'">({{ t.delay_days }}d{{ t.delay_days > 45 ? ', late' : '' }})</span>
              </td>
              <td class="px-3 py-2">
                <span class="font-medium">{{ t.ticker }}</span>
                <div class="text-sm text-ink-gray-5 truncate max-w-[16rem]">{{ t.asset_name }}</div>
              </td>
              <td class="px-3 py-2"><Badge :theme="t.side === 'buy' ? 'blue' : 'gray'" :label="t.side === 'buy' ? 'Buy' : 'Sell'" />
                <div v-if="t.owner && t.owner !== 'Self'" class="text-xs text-ink-gray-5 mt-0.5">{{ t.owner }}</div></td>
              <td class="px-3 py-2 text-sm text-ink-gray-7 whitespace-nowrap hidden md:table-cell">{{ t.amount_raw }}</td>
              <td class="px-3 py-2 text-right num whitespace-nowrap" :class="excessClass(t.trade_excess_6m)"
                :title="t.side === 'sell' ? 'For a sale, a negative number means the stock fell behind SPY after they sold' : ''">
                {{ signedPct(t.trade_excess_6m) }}<span v-if="t.trade_excess_6m !== null && !t.trade_complete" class="text-xs text-ink-gray-5"> so far</span>
              </td>
              <td class="px-3 py-2 text-right num whitespace-nowrap hidden md:table-cell" :title="stockSize(t).reason">{{ stockSize(t).short }}</td>
              <td class="px-3 py-2 hidden lg:table-cell">
                <a :href="t.source_url" target="_blank" rel="noopener" class="text-sm text-ink-blue-link hover:underline">Original ↗</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else class="mt-3" title="No trades match" :hint="`${m.name} has no ${side === 'all' ? '' : side + ' '}trades${ticker ? ' in ' + ticker.toUpperCase() : ''}.`">
        <Button label="Clear filters" @click="ticker = ''; side = 'all'" />
      </EmptyState>
      <div v-if="pages > 1" class="mt-3 flex items-center gap-2">
        <Button :disabled="p === 0" label="Previous" @click="p--" />
        <span class="text-sm text-ink-gray-6">Page {{ p + 1 }} of {{ pages }}</span>
        <Button :disabled="p >= pages - 1" label="Next" @click="p++" />
      </div>
      <p class="mt-3 text-sm text-ink-gray-5 leading-relaxed">
        "6 mo vs SPY" is the stock's return over the six months after the trade date minus SPY's return over the
        same period. For a sale, a negative number means the stock lagged after they sold, which was a good sale.
      </p>
    </section>

    <section id="other" class="scroll-mt-28" v-if="m.other_trades && m.other_trades.length">
      <h2 class="text-lg font-semibold text-ink-gray-9">Options, bonds, funds &amp; other ({{ num(m.n_other) }})</h2>
      <p class="mt-1 mb-3 text-sm text-ink-gray-5">Listed as disclosed. Not included in the performance figures above.</p>
      <OtherTradesTable :trades="m.other_trades" :odds="odds" :initial-class="m.other_counts.Options ? 'Options' : 'all'" />
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button, Skeleton, TabButtons, TextInput } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'
import StatTile from '../components/StatTile.vue'
import GrowthChart from '../components/GrowthChart.vue'
import VerdictBadge from '../components/VerdictBadge.vue'
import CoverageNote from '../components/CoverageNote.vue'
import OtherTradesTable from '../components/OtherTradesTable.vue'
import CopyCalculator from '../components/CopyCalculator.vue'
import MemberSearch from '../components/MemberSearch.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import { getMember, getSummary } from '../lib/data'
import { date, excessClass, money, num, pct, signedPct, tstat } from '../lib/format'
import { sizeTrade } from '../lib/risk'

const props = defineProps({ id: { type: String, required: true } })
const route = useRoute()
const m = ref(null)
const error = ref('')
const side = ref('all')
const ticker = ref('')
const p = ref(0)
const copied = ref(false)
const PER_PAGE = 50
const odds = ref(null)
getSummary().then((s) => { odds.value = s.odds }).catch(() => {})

watch(() => props.id, async (id) => {
  m.value = null; error.value = ''; p.value = 0; ticker.value = ''; side.value = 'all'
  try {
    m.value = await getMember(id)
    document.title = `${m.value.name} · Congress Trades Tracker`
    // Section deep links (#other) arrive before the sections exist; scroll once they do.
    if (route.hash) { await nextTick(); document.querySelector(route.hash)?.scrollIntoView({ block: 'start' }) }
  } catch (e) { error.value = `There is no member page for "${id}".` }
}, { immediate: true })

const views = [
  { key: 'trade', question: 'Did their stock picks beat the market?',
    explain: 'Buys each stock at the close on the day they traded and holds it six months.' },
  { key: 'filing', question: 'Could you have profited by copying them?',
    explain: 'Buys the trading day after the trade was publicly disclosed, as an ordinary investor could.' },
]
const sections = computed(() => [
  { id: 'summary', label: 'Summary' }, { id: 'calculator', label: 'Copy calculator' },
  ...(m.value?.series?.dates?.length > 4 || m.value?.top_buys?.length ? [{ id: 'performance', label: 'Performance' }] : []),
  ...(m.value?.trades?.length ? [{ id: 'stocks', label: 'Stock trades' }] : []),
  ...(m.value?.other_trades?.length ? [{ id: 'other', label: 'Options & more' }] : []),
])
const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

async function share() {
  const url = window.location.href
  try {
    if (navigator.share) { await navigator.share({ title: document.title, url }); return }
    await navigator.clipboard.writeText(url)
    copied.value = true; setTimeout(() => { copied.value = false }, 1500)
  } catch (e) { /* user dismissed the share sheet */ }
}

const filtered = computed(() => {
  const tk = ticker.value.trim().toUpperCase()
  return (m.value?.trades || []).filter((t) => (side.value === 'all' || t.side === side.value) && (!tk || t.ticker.startsWith(tk)))
})
watch([side, ticker], () => { p.value = 0 })
const pages = computed(() => Math.ceil(filtered.value.length / PER_PAGE))
const stockSize = (t) => sizeTrade({ assetClass: 'Stock', side: t.side,
  percentiles: m.value?.copy_odds?.return_percentiles || odds.value?.stocks.return_percentiles })
const page = computed(() => filtered.value.slice(p.value * PER_PAGE, (p.value + 1) * PER_PAGE))
</script>
