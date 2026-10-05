<template>
  <div v-if="error" class="space-y-3">
    <p class="text-ink-red-6">{{ error }}</p>
    <Button route="/members" label="← All members" />
  </div>
  <div v-else-if="!m" class="text-ink-gray-5">Loading…</div>
  <div v-else class="space-y-8">
    <div>
      <router-link to="/members" class="text-sm text-ink-gray-5 hover:underline">← All members</router-link>
      <h1 class="mt-2 text-2xl font-semibold text-ink-gray-9">{{ m.name }}</h1>
      <div class="mt-1 text-ink-gray-6">
        {{ m.party || 'Unknown party' }} · {{ m.chamber }}<span v-if="m.state"> · {{ m.state }}</span>
        · {{ num(m.n_trades) }} stock trades from {{ date(m.first_trade) }} to {{ date(m.last_trade) }}
      </div>
    </div>

    <CoverageNote />

    <section class="grid md:grid-cols-2 gap-3">
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
        <p class="mt-2 text-sm text-ink-gray-5">{{ v.explain }}</p>
      </div>
    </section>

    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatTile label="Stock purchases" :value="num(m.n_buys)" :sub="`${num(m.n_sells)} sales`" />
      <StatTile label="Hit rate" :value="pct(m.hit_rate, 0)" sub="Purchases that beat SPY over 6 months" />
      <StatTile label="Median disclosure delay" :value="`${m.median_delay_days} days`" :sub="`${pct(m.pct_late, 0)} filed after 45 days`" />
      <StatTile label="Disclosed volume" :value="money(m.volume_mid)" sub="Sum of range midpoints" />
    </section>

    <section v-if="m.series && m.series.dates && m.series.dates.length > 4" class="rounded-lg border border-outline-gray-2 p-4">
      <GrowthChart title="Growth of $1 while invested" subtitle="Their purchases at their own timing, held 6 months, vs SPY over the same days. Flat stretches are periods with no open positions."
        :dates="m.series.dates" :series="[
          { label: 'Their purchases', color: 'trade', values: m.series.member },
          { label: 'SPY', color: 'spy', values: m.series.spy },
        ]" />
    </section>

    <section v-if="m.top_buys.length">
      <h2 class="text-lg font-semibold text-ink-gray-9">Most-bought stocks</h2>
      <div class="mt-2 flex flex-wrap gap-2">
        <Badge v-for="t in m.top_buys" :key="t.ticker" theme="gray" size="lg" :label="`${t.ticker} × ${t.n}`" />
      </div>
    </section>

    <section>
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="text-lg font-semibold text-ink-gray-9">Trades</h2>
        <TabButtons v-model="side" :options="[{ label: 'All', value: 'all' }, { label: 'Buys', value: 'buy' }, { label: 'Sells', value: 'sell' }]" />
        <TextInput v-model="ticker" placeholder="Filter ticker…" class="w-36" aria-label="Filter by ticker" />
        <span class="text-sm text-ink-gray-5 ml-auto">{{ num(filtered.length) }} trades</span>
      </div>
      <div class="mt-3 overflow-x-auto rounded-lg border border-outline-gray-2">
        <table class="w-full text-base">
          <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
            <tr>
              <th class="px-3 py-2 text-left font-medium">Traded</th>
              <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Disclosed</th>
              <th class="px-3 py-2 text-left font-medium">Stock</th>
              <th class="px-3 py-2 text-left font-medium">Type</th>
              <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Amount</th>
              <th class="px-3 py-2 text-right font-medium">6 mo vs SPY</th>
              <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">Filing</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(t, i) in page" :key="i" class="border-t border-outline-gray-1">
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
              <td class="px-3 py-2 hidden lg:table-cell">
                <a :href="t.source_url" target="_blank" rel="noopener" class="text-sm text-ink-blue-link hover:underline">Original ↗</a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="pages > 1" class="mt-3 flex items-center gap-2">
        <Button :disabled="p === 0" label="Previous" @click="p--" />
        <span class="text-sm text-ink-gray-6">Page {{ p + 1 }} of {{ pages }}</span>
        <Button :disabled="p >= pages - 1" label="Next" @click="p++" />
      </div>
      <p class="mt-3 text-sm text-ink-gray-5 leading-relaxed">
        "6 mo vs SPY" is the stock's return over the six months after the trade date minus SPY's return over the
        same period. For a sale, a negative number means the stock lagged after they sold, which was a good
        sale.
      </p>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, TabButtons, TextInput } from 'frappe-ui'
import StatTile from '../components/StatTile.vue'
import GrowthChart from '../components/GrowthChart.vue'
import VerdictBadge from '../components/VerdictBadge.vue'
import CoverageNote from '../components/CoverageNote.vue'
import { getMember } from '../lib/data'
import { date, excessClass, money, num, pct, signedPct, tstat } from '../lib/format'

const props = defineProps({ id: { type: String, required: true } })
const m = ref(null)
const error = ref('')
const side = ref('all')
const ticker = ref('')
const p = ref(0)
const PER_PAGE = 50

watch(() => props.id, async (id) => {
  m.value = null; error.value = ''; p.value = 0
  try {
    m.value = await getMember(id)
    document.title = `${m.value.name} · Congress Trades Tracker`
  } catch (e) { error.value = `No member found for "${id}".` }
}, { immediate: true })

const views = [
  { key: 'trade', question: 'Did their stock picks beat the market?',
    explain: 'Buys each stock at the close on the day they traded and holds it six months.' },
  { key: 'filing', question: 'Could you have profited by copying them?',
    explain: 'Buys the trading day after the trade was publicly disclosed, as an ordinary investor could.' },
]

const filtered = computed(() => {
  const tk = ticker.value.trim().toUpperCase()
  return (m.value?.trades || []).filter((t) => (side.value === 'all' || t.side === side.value) && (!tk || t.ticker.startsWith(tk)))
})
watch([side, ticker], () => { p.value = 0 })
const pages = computed(() => Math.ceil(filtered.value.length / PER_PAGE))
const page = computed(() => filtered.value.slice(p.value * PER_PAGE, (p.value + 1) * PER_PAGE))
</script>
