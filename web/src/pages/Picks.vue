<template>
  <div class="space-y-6">
    <PageHeader title="Your picks">
      <span class="inline-flex items-center gap-1 rounded-2 bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7 mr-1">🔒 Private</span>
      A call for every trade disclosed in the last <span v-if="d">{{ d.window_days }}</span> days, sized to your risk
      settings<span v-if="d">. Prices as of {{ date(d.asof) }}, rebuilt {{ d.generated }}</span>. Older trades are left out:
      waiting after a disclosure didn't change outcomes, but trades filed late tended to lose.
    </PageHeader>

    <div v-if="locked" class="rounded-lg border border-outline-gray-2 p-6 max-w-lg space-y-3">
      <div class="font-medium text-ink-gray-9">This page needs the password</div>
      <p class="text-sm text-ink-gray-6">Open it as a full page load so the browser can ask for it.</p>
      <Button href="/picks" label="Sign in to picks" />
    </div>
    <ErrorState v-else-if="error" :message="error" />
    <div v-else-if="!d" class="space-y-4" aria-busy="true">
      <Skeleton class="h-20 rounded-lg" /><Skeleton class="h-28 rounded-lg" />
      <Skeleton v-for="i in 3" :key="i" class="h-40 rounded-lg" />
    </div>
    <template v-else>
      <Alert v-if="!m.validated" theme="amber" title="No “Buy” calls right now: the edge isn't proven">
        <template #description>
          Tested on {{ num(m.test.n) }} trades from {{ m.test.start.slice(0, 4) }} on, the model's top-rated fifth beat SPY by
          {{ signedPct(m.buy_group.mean_excess_6m) }} over 6 months (t = {{ m.buy_group.t.toFixed(1) }}, short of the t ≥ 2 bar)
          and won only {{ pct(m.buy_group.hit_rate, 0) }} of the time. So top-rated trades are marked <strong>Watch</strong>, not Buy.
          The <strong>Don't buy</strong> calls are well supported: those trades trailed SPY by
          {{ signedPct(m.rest.mean_excess_6m) }} (t = {{ m.rest.t.toFixed(1) }}).
        </template>
      </Alert>
      <Alert v-else theme="green" title="Model passed its out-of-sample test">
        <template #description>
          Top-rated trades beat SPY by {{ signedPct(m.buy_group.mean_excess_6m) }} over 6 months in testing
          (t = {{ m.buy_group.t.toFixed(1) }}), so they are marked Buy.
        </template>
      </Alert>

      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <button v-for="g in groupTiles" :key="g.key" class="text-left rounded-lg border p-4 transition-colors"
          :class="tab === g.key ? 'border-outline-gray-5 bg-surface-gray-1' : 'border-outline-gray-2 hover:bg-surface-gray-1'"
          :aria-pressed="tab === g.key" @click="tab = g.key">
          <div class="text-sm text-ink-gray-5">{{ g.label }}</div>
          <div class="mt-1 text-2xl font-semibold num text-ink-gray-9">{{ count(g.key) }}</div>
          <div class="mt-1 text-sm text-ink-gray-6">{{ g.sub }}</div>
        </button>
      </div>

      <RiskSettings />

      <div class="rounded-lg border border-outline-gray-2 p-3 text-sm text-ink-gray-7">
        If you bought every {{ m.validated ? 'Buy' : 'Watch' }} pick at the suggested size:
        <strong class="text-ink-gray-9 num">{{ usd(totalIn) }}</strong> invested
        ({{ pct(totalIn / Math.max(1, Number(risk.portfolio)), 0) }} of your portfolio), with up to
        <strong class="text-ink-gray-9 num">{{ usd(totalRisk) }}</strong> at risk in a bad case.
        <span v-if="totalIn > Number(risk.portfolio) * 0.5" class="text-ink-amber-7">That is a lot in one strategy; consider fewer picks.</span>
      </div>

      <ul class="space-y-3">
        <li v-for="(r, i) in shown" :key="i" class="rounded-lg border border-outline-gray-2 p-4">
          <div class="flex flex-wrap items-start gap-x-4 gap-y-2">
            <Badge :theme="REC[r.rec].theme" :variant="REC[r.rec].variant" size="lg" :label="REC[r.rec].label" />
            <div class="min-w-0">
              <div class="font-semibold text-ink-gray-9">
                {{ r.ticker || '—' }} <span class="font-normal text-ink-gray-6">{{ r.asset_name }}</span>
                <Badge v-if="r.asset_class !== 'Stock'" class="ml-1" theme="gray" size="sm" :label="r.asset_class" />
              </div>
              <div class="text-sm text-ink-gray-6">
                <router-link :to="`/members/${r.member_id}`" class="hover:underline">{{ r.member }}</router-link>
                · {{ r.side === 'buy' ? 'bought' : 'sold' }} {{ r.amount_raw }} on {{ date(r.tx_date) }}
                · disclosed {{ date(r.filing_date) }}
                <span :class="r.delay_days > d.late_filing_days ? 'text-ink-amber-7' : ''">({{ r.delay_days }}d later)</span>
                <span v-if="r.option"> · {{ optionText(r.option) }}</span>
              </div>
            </div>
            <div v-if="r.confidence !== undefined" class="ml-auto text-right">
              <div class="text-sm text-ink-gray-5">Chance it beats SPY (6 mo)</div>
              <div class="text-xl font-semibold num text-ink-gray-9">{{ pct(r.confidence, 0) }}</div>
              <div class="text-xs text-ink-gray-5 num">similar trades averaged {{ signedPct(r.expected_excess_6m) }} vs SPY</div>
            </div>
            <div v-if="sized(r)" class="text-right" :class="r.confidence === undefined ? 'ml-auto' : ''">
              <div class="text-sm text-ink-gray-5">{{ r.rec === 'not_rated' ? 'Most to put in, if you buy' : 'Put in at most' }}</div>
              <div class="text-xl font-semibold num text-ink-gray-9" :title="sized(r).reason">{{ sized(r).short }}</div>
            </div>
          </div>
          <ul v-if="r.reasons && r.reasons.length" class="mt-3 list-disc pl-5 text-sm text-ink-gray-7 space-y-0.5">
            <li v-for="(x, j) in r.reasons" :key="j">{{ x }}</li>
          </ul>
          <div v-if="r.news && r.news.length" class="mt-3">
            <div class="text-xs font-medium text-ink-gray-5 uppercase tracking-wide">Recent news</div>
            <ul class="mt-1 space-y-0.5">
              <li v-for="(n, j) in r.news" :key="j" class="text-sm">
                <a :href="n.link" target="_blank" rel="noopener" class="text-ink-blue-link hover:underline">{{ n.title }}</a>
                <span class="text-ink-gray-5"> · {{ n.publisher }}, {{ date(n.date) }}</span>
                <Badge v-if="n.takeover" class="ml-1" theme="red" size="sm" label="Deal news" />
              </li>
            </ul>
          </div>
          <a :href="r.source_url" target="_blank" rel="noopener" class="mt-2 inline-block text-xs text-ink-blue-link hover:underline">Original filing ↗</a>
        </li>
        <li v-if="!shown.length"><EmptyState title="Nothing in this group right now" /></li>
      </ul>
      <p class="text-xs text-ink-gray-5 leading-relaxed">
        For your own use. Based on historical patterns in disclosure data; past results don't guarantee future
        ones, and the calls carry real uncertainty as shown. Not investment advice.
      </p>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Alert, Badge, Button, Skeleton } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'
import RiskSettings from '../components/RiskSettings.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import { risk, sizeTrade, TOLERANCES } from '../lib/risk'
import { date, num, pct, signedPct, usd } from '../lib/format'

const REC = {
  buy: { label: 'Buy', theme: 'green', variant: 'solid' },
  watch: { label: 'Watch', theme: 'amber', variant: 'subtle' },
  sell_if_owned: { label: 'Sell if you own it', theme: 'blue', variant: 'subtle' },
  dont_buy: { label: "Don't buy", theme: 'red', variant: 'subtle' },
  not_rated: { label: 'Not rated', theme: 'gray', variant: 'subtle' },
  expired: { label: 'Expired', theme: 'gray', variant: 'subtle' },
  'n/a': { label: 'n/a', theme: 'gray', variant: 'subtle' },
}
const GROUPS = { picks: ['buy', 'watch'], sell: ['sell_if_owned'], dont: ['dont_buy'], other: ['not_rated', 'expired', 'n/a'] }

const d = ref(null)
const error = ref('')
const locked = ref(false)
const tab = ref('picks')
onMounted(async () => {
  try {
    const r = await fetch('/picks/recs.json', { credentials: 'same-origin', cache: 'no-store' })
    if (r.status === 401) { locked.value = true; return }
    if (!r.ok) throw new Error(`Could not load picks (${r.status})`)
    d.value = await r.json()
  } catch (e) { error.value = e.message }
})

const m = computed(() => d.value.model)
const count = (g) => (d.value?.rows || []).filter((r) => GROUPS[g].includes(r.rec)).length
const groupTiles = computed(() => [
  { key: 'picks', label: m.value?.validated ? 'Buy' : 'Watch', sub: m.value?.validated ? 'Passed the test' : 'Top-rated, unproven edge' },
  { key: 'sell', label: 'Sell if you own it', sub: 'Members sold these' },
  { key: 'dont', label: "Don't buy", sub: 'Low-rated or filed late' },
  { key: 'other', label: 'Not rated', sub: 'Options, funds, expired, n/a' },
])
const shown = computed(() => (d.value?.rows || []).filter((r) => GROUPS[tab.value].includes(r.rec)))

function sized(r) {
  if (!['buy', 'watch', 'not_rated'].includes(r.rec) || r.side !== 'buy') return null
  return sizeTrade({ assetClass: r.asset_class, side: 'buy', percentiles: r.percentiles || d.value.base_percentiles })
}
const picks = computed(() => (d.value?.rows || []).filter((r) => GROUPS.picks.includes(r.rec)))
const totalIn = computed(() => picks.value.reduce((s, r) => s + (sized(r)?.amount || 0), 0))
const totalRisk = computed(() => {
  const tol = TOLERANCES[risk.tolerance] || TOLERANCES.moderate
  return picks.value.reduce((s, r) => {
    const p = (r.percentiles || d.value.base_percentiles)[tol.pctl]
    return s + (sized(r)?.amount || 0) * Math.max(0.05, -(p ?? -0.5))
  }, 0)
})
const optionText = (o) => [o.type, o.strike ? `$${o.strike} strike` : null, o.expiry ? `exp ${o.expiry}` : null].filter(Boolean).join(' · ')
</script>
