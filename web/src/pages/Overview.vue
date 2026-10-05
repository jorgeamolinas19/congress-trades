<template>
  <ErrorState v-if="error" :message="error" />
  <div v-else-if="!s" class="space-y-8" aria-busy="true">
    <div class="space-y-3 max-w-3xl"><Skeleton class="h-8 w-3/4 rounded-2" /><Skeleton class="h-4 w-full rounded-2" /><Skeleton class="h-4 w-5/6 rounded-2" /></div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3"><Skeleton v-for="i in 4" :key="i" class="h-24 rounded-lg" /></div>
    <Skeleton class="h-80 rounded-lg" />
  </div>
  <div v-else class="space-y-12">
    <!-- Hero: the answer, then the three things a visitor can do. -->
    <section>
      <div class="eyebrow text-ink-gray-5">
        {{ num(s.study.sample.n_trades) }} disclosed stock trades · {{ s.study.sample.n_members }} members · 2014 to {{ s.data_through.slice(0, 4) }}
      </div>
      <h1 class="mt-2 text-3xl md:text-4xl font-semibold tracking-tight text-ink-gray-9 max-w-3xl">Do members of Congress beat the market?</h1>
      <div class="mt-4 flex flex-wrap items-baseline gap-x-6 gap-y-2 font-mono">
        <div><span class="text-4xl md:text-5xl font-semibold text-ink-gray-9 num">{{ pct(filing.ann_return) }}</span><span class="ml-2 text-sm text-ink-gray-5 uppercase tracking-wider">/ yr copying Congress</span></div>
        <div><span class="text-4xl md:text-5xl font-semibold text-ink-gray-6 num">{{ pct(spy.ann_return) }}</span><span class="ml-2 text-sm text-ink-gray-5 uppercase tracking-wider">/ yr S&amp;P 500</span></div>
      </div>
      <p class="mt-3 text-lg text-ink-gray-7 leading-relaxed max-w-3xl">
        Not on average, and not in a way you could copy. Buying what Congress buys, the day it is disclosed, would have
        returned <strong class="text-ink-gray-9">{{ pct(filing.ann_return) }} a year</strong> against
        {{ pct(spy.ann_return) }} for the S&amp;P 500, with no statistically meaningful edge after adjusting for risk.
        But averages hide a lot. Look up any member, see what was just disclosed, or size a copy trade to your own risk.
      </p>
      <div class="mt-6 grid sm:grid-cols-3 gap-3">
        <router-link v-for="c in ctas" :key="c.to" :to="c.to"
          class="group rounded-lg border border-outline-gray-2 p-4 hover:border-outline-gray-4 hover:bg-surface-gray-1 transition-colors">
          <div class="eyebrow text-ink-green-6" aria-hidden="true">{{ c.icon }}</div>
          <div class="mt-2 font-semibold text-ink-gray-9 group-hover:underline">{{ c.title }}</div>
          <div class="mt-1 text-sm text-ink-gray-6">{{ c.sub }}</div>
        </router-link>
      </div>
    </section>

    <section>
      <h2 class="text-xl font-semibold text-ink-gray-9">The headline numbers</h2>
      <p class="mt-1 text-sm text-ink-gray-5">Every disclosed purchase held six months, equal-weighted, {{ s.study.window.start.slice(0, 4) }}–{{ s.study.window.end.slice(0, 4) }}. Alpha is what's left after the Fama-French 5 + momentum factors.</p>
      <div class="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Copying at disclosure" :value="`${pct(filing.ann_return)} / yr`"
          :sub="`Alpha ${signedPct(filingReg.alpha_ann)} (t = ${tstat(filingReg.alpha_t)}): not distinguishable from zero`" />
        <StatTile label="Members' own timing" :value="`${pct(trade.ann_return)} / yr`"
          :sub="`Alpha ${signedPct(tradeReg.alpha_ann)} (t = ${tstat(tradeReg.alpha_t)}): no edge even before disclosure`" />
        <StatTile label="S&P 500 (SPY)" :value="`${pct(spy.ann_return)} / yr`" sub="The benchmark over the same days" />
        <StatTile label="Median disclosure delay" :value="`${s.study.sample.median_delay_days} days`"
          :sub="`${pct(s.study.sample.pct_filed_late_over_45d, 0)} filed after the 45-day deadline`" />
      </div>
      <CoverageNote class="mt-3 max-w-3xl" />
    </section>

    <section class="rounded-lg border border-outline-gray-2 p-4">
      <GrowthChart title="Growth of $1" :subtitle="`Every disclosed purchase held 6 months, ${s.study.window.start} to ${s.study.window.end}`"
        :dates="s.growth.dates" :series="[
          { label: 'Members\' timing', color: 'trade', values: s.growth.trade },
          { label: 'Copying at disclosure', color: 'filing', values: s.growth.filing },
          { label: 'SPY', color: 'spy', values: s.growth.spy },
        ]" />
    </section>

    <section>
      <h2 class="text-xl font-semibold text-ink-gray-9">Member by member</h2>
      <p class="mt-2 text-ink-gray-7 max-w-3xl leading-relaxed">
        {{ s.members_with_verdict }} members made enough stock purchases to judge. On their own timing,
        <strong class="text-ink-gray-9">{{ vc.beat + vc.beat_significant }} beat SPY and {{ vc.lagged + vc.lagged_significant }} trailed it</strong>,
        about the split a coin flip gives. {{ s.significant_unadjusted.trade }} look "statistically significant" alone, but roughly
        {{ s.expected_by_chance }} would by luck at that threshold. After correcting for testing {{ s.members_with_verdict }} members at once,
        <strong class="text-ink-gray-9">{{ vc.beat_significant }} beat the market by more than luck explains</strong>.
      </p>
      <div class="mt-4 grid sm:grid-cols-2 gap-3">
        <div class="rounded-lg border border-outline-gray-2 p-4">
          <div class="text-sm font-medium text-ink-gray-8">Biggest outperformers (own timing)</div>
          <MiniBoard :members="top" class="mt-2" />
        </div>
        <div class="rounded-lg border border-outline-gray-2 p-4">
          <div class="text-sm font-medium text-ink-gray-8">Biggest underperformers (own timing)</div>
          <MiniBoard :members="bottom" class="mt-2" />
        </div>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <Button route="/members" label="See all members →" />
        <Button variant="ghost" route="/members?view=filing" label="Rank by what a copier earned" />
      </div>
    </section>

    <section class="grid lg:grid-cols-2 gap-8">
      <div>
        <h2 class="text-xl font-semibold text-ink-gray-9">Most-bought stocks, last 12 months</h2>
        <p class="text-sm text-ink-gray-5 mt-1">Ranked by how many different members bought.</p>
        <table class="mt-3 w-full text-base">
          <thead><tr class="text-left text-sm text-ink-gray-5 border-b border-outline-gray-2">
            <th class="py-2 font-normal">Ticker</th><th class="py-2 font-normal">Company</th>
            <th class="py-2 font-normal text-right">Members</th><th class="py-2 font-normal text-right">Buys</th></tr></thead>
          <tbody>
            <tr v-for="t in s.most_bought.slice(0, 12)" :key="t.ticker" class="border-b border-outline-gray-1">
              <td class="py-2 font-medium">{{ t.ticker }}</td>
              <td class="py-2 text-ink-gray-6 truncate max-w-[14rem]">{{ t.name }}</td>
              <td class="py-2 text-right num">{{ t.members }}</td><td class="py-2 text-right num">{{ t.n }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div>
        <h2 class="text-xl font-semibold text-ink-gray-9">Latest disclosures</h2>
        <p class="text-sm text-ink-gray-5 mt-1">Filings received through {{ date(s.data_through) }}.</p>
        <ul class="mt-3 divide-y divide-outline-gray-1">
          <li v-for="(t, i) in s.recent.slice(0, 10)" :key="i" class="py-2 flex items-center gap-3 text-base">
            <Badge :theme="t.side === 'buy' ? 'blue' : 'gray'" :label="t.side === 'buy' ? 'Buy' : 'Sell'" />
            <span class="font-medium w-14 shrink-0">{{ t.ticker }}</span>
            <router-link :to="`/members/${t.member_id}`" class="truncate text-ink-gray-7 hover:underline">{{ t.member }}</router-link>
            <span class="ml-auto text-sm text-ink-gray-5 whitespace-nowrap">{{ t.amount_raw }}</span>
          </li>
        </ul>
        <div class="mt-3"><Button route="/trades" label="All recent trades →" /></div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Skeleton } from 'frappe-ui'
import StatTile from '../components/StatTile.vue'
import GrowthChart from '../components/GrowthChart.vue'
import MiniBoard from '../components/MiniBoard.vue'
import CoverageNote from '../components/CoverageNote.vue'
import ErrorState from '../components/ErrorState.vue'
import { getMembers, getSummary } from '../lib/data'
import { date, num, pct, signedPct, tstat } from '../lib/format'

const s = ref(null)
const members = ref([])
const error = ref('')
onMounted(async () => {
  try { [s.value, members.value] = await Promise.all([getSummary(), getMembers()]) } catch (e) { error.value = e.message }
})

const ctas = [
  { to: '/members', icon: '01 / MEMBERS', title: 'Look up a member', sub: 'Did their picks beat the market? Could you have profited by copying them?' },
  { to: '/trades', icon: '02 / TAPE', title: 'See the latest trades', sub: 'What was just disclosed, and the most to put in at your risk level.' },
  { to: '/other', icon: '03 / DERIVATIVES', title: 'Options, bonds & funds', sub: 'Everything that isn\'t common stock, including the famous options trades.' },
]
const trade = computed(() => s.value.study.summary.trade_date)
const filing = computed(() => s.value.study.summary.filing_date)
const spy = computed(() => s.value.study.summary.spy)
const reg = (p) => s.value.study.regressions.find((r) => r.portfolio === p)
const tradeReg = computed(() => reg('trade_date'))
const filingReg = computed(() => reg('filing_date'))
const vc = computed(() => s.value.verdict_counts.trade)
const judged = computed(() => members.value.filter((m) => m.verdict_trade !== 'insufficient')
  .sort((a, b) => b.trade.excess_ann - a.trade.excess_ann))
const top = computed(() => judged.value.slice(0, 5))
const bottom = computed(() => judged.value.slice(-5).reverse())
</script>
