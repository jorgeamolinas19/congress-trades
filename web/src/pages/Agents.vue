<template>
  <div class="space-y-6">
    <PageHeader title="Agent desk">
      <span class="inline-flex items-center gap-1 rounded-2 bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7 mr-1">🔒 Private</span>
      An AI trading team (<a class="text-ink-blue-link hover:underline" href="https://github.com/TauricResearch/TradingAgents" target="_blank" rel="noopener">TradingAgents</a>:
      analysts, a bull and a bear researcher, a trader and a risk manager) reviews new congressional purchases. Its calls
      are traded with <strong>fake money</strong> so we can see whether they work, next to SPY and the statistical picks.
    </PageHeader>

    <div v-if="locked" class="rounded-lg border border-outline-gray-2 p-6 max-w-lg space-y-3">
      <div class="font-medium text-ink-gray-9">This page needs the password</div>
      <p class="text-sm text-ink-gray-6">Open it as a full page load so the browser can ask for it.</p>
      <Button href="/agents" label="Sign in" />
    </div>
    <ErrorState v-else-if="error" :message="error" />
    <div v-else-if="!d" class="space-y-4" aria-busy="true">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3"><Skeleton v-for="i in 4" :key="i" class="h-24 rounded-lg" /></div>
      <Skeleton class="h-80 rounded-lg" /><Skeleton class="h-40 rounded-lg" />
    </div>
    <template v-else>
      <Alert v-if="d.note || d.budget.paused_because" theme="amber" :title="d.note ? 'No new analyses ran' : 'Analyses are paused'">
        <template #description>{{ d.note || d.budget.paused_because }}</template>
      </Alert>

      <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6">
        <strong class="text-ink-gray-8">An experiment, not advice.</strong>
        With a few analyses a week, luck dominates the results for a long time. Watch the trend over months, not days.
        Every call is kept exactly as made; nothing is re-run to change an answer.
      </div>

      <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Agent desk" :value="hasAgents ? usd(a.value) : '—'"
          :sub="hasAgents ? `${signedPct(a.return)} · ${a.n_closed} closed, ${a.n_open} open` : 'No analyses yet'"
          :value-class="hasAgents ? excessClass(a.return) : 'text-ink-gray-5'" />
        <StatTile label="Statistical picks" :value="s.value ? usd(s.value) : '—'"
          :sub="`${signedPct(s.return)} · ${s.n_closed} closed, ${s.n_open} open`" :value-class="excessClass(s.return)" />
        <StatTile label="SPY, same days" :value="d.accounts.spy.value ? usd(d.accounts.spy.value) : '—'"
          :sub="signedPct(d.accounts.spy.return)" />
        <StatTile label="LLM budget this month" :value="`${usd(d.budget.spent)} / ${usd(d.budget.cap)}`"
          :sub="`${d.budget.runs} ${d.budget.runs === 1 ? 'analysis' : 'analyses'} · about ${usd(d.budget.est_run)} each`" />
      </section>

      <section v-if="chart.dates.length > 1" class="rounded-lg border border-outline-gray-2 p-4">
        <GrowthChart title="Paper accounts: $1,000 each" unit="usd" :y-min="chart.yMin"
          :subtitle="`Started ${date(d.start)}. Prices through ${date(d.data_date)}. Trades fill at the next close, with ${pct(d.rules.slippage, 1)} slippage.`"
          :dates="chart.dates" :series="chart.series" />
      </section>
      <EmptyState v-else title="The chart appears once the accounts have a second day of data"
        hint="The accounts start at the first analysis or statistical pick." />

      <TabButtons v-model="tab" :options="tabs" />

      <!-- Decisions -->
      <ul v-if="tab === 'decisions'" class="space-y-3">
        <li v-for="x in d.decisions" :key="x.id" class="rounded-lg border border-outline-gray-2 p-4">
          <div class="flex flex-wrap items-start gap-x-4 gap-y-2">
            <Badge :theme="RATING[x.rating]?.theme || 'gray'" :variant="RATING[x.rating]?.variant || 'subtle'" size="lg" :label="x.error ? 'Stopped' : x.rating" />
            <div class="min-w-0">
              <div class="font-semibold text-ink-gray-9">{{ x.ticker }} <span class="font-normal text-ink-gray-6">{{ x.name }}</span></div>
              <div class="text-sm text-ink-gray-6">
                <router-link :to="`/members/${x.member_id}`" class="hover:underline">{{ x.member }}</router-link>
                bought {{ x.amount_raw }}, disclosed {{ date(x.filing_date) }} · analyzed as of {{ date(x.data_date) }}
              </div>
            </div>
            <div class="ml-auto text-right text-sm">
              <div :class="outcomeClass(x.outcome.status)">{{ outcomeLabel(x) }}</div>
              <div v-if="x.stats_rec && !x.error" class="text-xs text-ink-gray-5">
                Stats model: {{ x.stats_rec === 'watch' ? 'Watch' : x.stats_rec === 'buy' ? 'Buy' : "Don't buy" }}
                <span :class="verdictClass(x)">· {{ verdictLabel(x) }}</span>
              </div>
            </div>
          </div>
          <p v-if="x.error" class="mt-2 text-sm text-ink-amber-7">{{ x.error }}</p>
          <details v-if="Object.keys(x.sections || {}).length" class="mt-3 group">
            <summary class="cursor-pointer text-sm text-ink-blue-link hover:underline select-none">Read the reasoning</summary>
            <div class="mt-3 space-y-3">
              <div v-for="[k, title] in SECTIONS.filter(([k]) => x.sections[k])" :key="k">
                <div class="eyebrow text-ink-gray-5">{{ title }}</div>
                <div class="mt-1 text-sm text-ink-gray-7 leading-relaxed whitespace-pre-wrap" v-html="md(x.sections[k])" />
              </div>
            </div>
          </details>
          <div class="mt-3 text-xs text-ink-gray-5 num">
            est. cost {{ usd(x.cost_usd) }} · {{ kfmt(x.tokens_in) }} tokens in, {{ kfmt(x.tokens_out) }} out · {{ x.seconds }}s ·
            {{ x.models?.quick }} / {{ x.models?.deep }} · analyzed {{ x.run_at }}
            <a v-if="x.source_url" :href="x.source_url" target="_blank" rel="noopener" class="ml-2 text-ink-blue-link hover:underline">Original filing ↗</a>
          </div>
        </li>
        <li v-if="!d.decisions.length">
          <EmptyState title="No analyses yet" hint="The first one runs on the next daily update once the OpenAI account has credits." />
        </li>
      </ul>

      <!-- Positions / closed trades -->
      <template v-else>
        <div class="flex items-center gap-3">
          <TabButtons v-model="acct" :options="[{ label: 'Agent desk', value: 'agents' }, { label: 'Statistical picks', value: 'stats' }]" />
          <span class="text-sm text-ink-gray-5">{{ acct === 'agents' ? 'Positions the agents opened.' : 'Positions from the statistical model\'s Watch/Buy picks.' }}</span>
        </div>
        <div v-if="rows.length" class="overflow-x-auto rounded-lg border border-outline-gray-2">
          <table class="w-full text-base">
            <thead class="bg-surface-gray-1 text-sm text-ink-gray-6"><tr>
              <th class="px-3 py-2 text-left font-medium">Stock</th>
              <th class="px-3 py-2 text-left font-medium">Entered</th>
              <th class="px-3 py-2 text-right font-medium">In at</th>
              <th class="px-3 py-2 text-right font-medium">{{ tab === 'open' ? 'Now' : 'Out at' }}</th>
              <th class="px-3 py-2 text-right font-medium">P&amp;L</th>
              <th class="px-3 py-2 text-left font-medium">{{ tab === 'open' ? 'Closes' : 'Closed' }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="(p, i) in rows" :key="i" class="border-t border-outline-gray-1">
                <td class="px-3 py-2 font-medium">{{ p.ticker }}</td>
                <td class="px-3 py-2 whitespace-nowrap">{{ date(p.entry_date) }}</td>
                <td class="px-3 py-2 text-right num">{{ usd2(p.entry_price) }}</td>
                <td class="px-3 py-2 text-right num">{{ usd2(tab === 'open' ? p.price : p.exit_price) }}</td>
                <td class="px-3 py-2 text-right num whitespace-nowrap" :class="excessClass(p.pnl)">{{ signed(p.pnl) }} <span class="text-ink-gray-5">({{ signedPct(p.pnl_pct) }})</span></td>
                <td class="px-3 py-2 whitespace-nowrap">{{ tab === 'open' ? `≈ ${date(p.exit_due)}` : `${date(p.exit_date)} · ${p.reason === 'time' ? `${p.days_held}-day exit` : 'sell signal'}` }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-else :title="tab === 'open' ? 'No open positions' : 'No closed trades yet'"
          :hint="tab === 'open' ? 'Positions appear after the first Buy fills at a close.' : `Positions close ${d.rules.hold_days} trading days after entry, or on a sell signal.`" />
      </template>

      <details class="text-sm text-ink-gray-5 max-w-3xl">
        <summary class="cursor-pointer text-ink-gray-7">Rules of the paper accounts</summary>
        <ul class="mt-2 list-disc pl-5 space-y-1">
          <li>Each account starts with {{ usd(d.rules.start_cash) }} on {{ d.start || 'its first decision' }}. No leverage, no shorting.</li>
          <li>A Buy or Overweight puts {{ usd(d.rules.position_usd) }} into the stock, at most {{ d.rules.max_positions }} positions open, one per stock.</li>
          <li>A Sell or Underweight closes the position if held; Hold does nothing.</li>
          <li>Every trade fills at the <strong>close of the first trading day after</strong> the analysis date, so a call never uses prices it could already see, with {{ pct(d.rules.slippage, 1) }} slippage against you.</li>
          <li>Positions close automatically {{ d.rules.hold_days }} trading days after entry.</li>
          <li>Models: {{ d.models.quick }} (analysts and debaters), {{ d.models.deep }} (managers). Costs are estimated from list prices plus 25% and capped at {{ usd(d.budget.cap) }} a month.</li>
          <li>Each analysis is told what the paper account already holds, so it can tell adding to a position from opening one.</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Alert, Badge, Button, Skeleton, TabButtons } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'
import StatTile from '../components/StatTile.vue'
import GrowthChart from '../components/GrowthChart.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import { date, excessClass, pct, signedPct, usd } from '../lib/format'

const RATING = {
  Buy: { theme: 'green', variant: 'solid' }, Overweight: { theme: 'green', variant: 'subtle' },
  Hold: { theme: 'gray', variant: 'subtle' }, Underweight: { theme: 'red', variant: 'subtle' },
  Sell: { theme: 'red', variant: 'solid' }, REVIEW: { theme: 'amber', variant: 'subtle' },
}
const SECTIONS = [
  ['final', "Portfolio manager's decision"], ['trader', "Trader's plan"], ['research_plan', "Research manager's plan"],
  ['bull', 'Bull researcher'], ['bear', 'Bear researcher'], ['risk_aggressive', 'Risk: aggressive view'],
  ['risk_conservative', 'Risk: conservative view'], ['risk_neutral', 'Risk: neutral view'],
  ['market', 'Market analyst'], ['news', 'News analyst'], ['fundamentals', 'Fundamentals analyst'], ['sentiment', 'Sentiment analyst'],
]

const d = ref(null)
const error = ref('')
const locked = ref(false)
const tab = ref('decisions')
const acct = ref('agents')
onMounted(async () => {
  try {
    const r = await fetch('/picks/agents.json', { credentials: 'same-origin', cache: 'no-store' })
    if (r.status === 401) { locked.value = true; return }
    if (r.status === 404) { error.value = 'The agent desk has no data yet. It appears after the next daily update.'; return }
    if (!r.ok) throw new Error(`Could not load the agent desk (${r.status})`)
    d.value = await r.json()
  } catch (e) { error.value = e.message }
})

const a = computed(() => d.value.accounts.agents)
const s = computed(() => d.value.accounts.stats)
const hasAgents = computed(() => d.value.decisions.length > 0)

// Chart: drop a line that has no values at all (e.g. agents, before the first trade-eligible decision).
const chart = computed(() => {
  const ser = d.value.series
  const lines = [
    { label: 'Agent desk', color: 'agents', values: ser.map((r) => r.agents) },
    { label: 'Statistical picks', color: 'stats', values: ser.map((r) => r.stats) },
    { label: 'SPY', color: 'spy', values: ser.map((r) => r.spy) },
  ].filter((l) => l.values.some((v) => v !== null && v !== undefined))
  const vals = lines.flatMap((l) => l.values).filter((v) => v !== null && v !== undefined)
  // Zoom the axis to the data, so a few percent of movement is visible rather than a flat line near $1,000.
  const yMin = vals.length ? Math.floor((Math.min(...vals) * 0.985) / 10) * 10 : undefined
  return { dates: ser.map((r) => r.date), series: lines, yMin }
})

const rows = computed(() => {
  const acc = d.value.accounts[acct.value]
  return tab.value === 'open' ? acc.positions : [...acc.closed].reverse()
})
const tabs = computed(() => [
  { label: `Decisions (${d.value?.decisions.length ?? 0})`, value: 'decisions' },
  { label: `Open (${d.value?.accounts[acct.value].positions.length ?? 0})`, value: 'open' },
  { label: `Closed (${d.value?.accounts[acct.value].closed.length ?? 0})`, value: 'closed' },
])

const usd2 = (v) => (v === null || v === undefined ? '—' : `$${Number(v).toFixed(2)}`)
const signed = (v) => `${v >= 0 ? '+' : '−'}$${Math.abs(v).toFixed(2)}`
const kfmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}K` : `${n}`)
const statsBullish = (x) => ['buy', 'watch'].includes(x.stats_rec)
const verdictLabel = (x) => (x.action === 'hold' ? 'agents neutral' : (x.action === 'buy') === statsBullish(x) ? 'agrees' : 'disagrees')
const verdictClass = (x) => (x.action === 'hold' ? 'text-ink-gray-5' : (x.action === 'buy') === statsBullish(x) ? 'text-ink-green-6' : 'text-ink-amber-7')
const outcomeLabel = (x) => ({ filled: `Paper trade: ${x.outcome.note} (${date(x.outcome.date)})`, skipped: `No trade: ${x.outcome.note}`,
  pending: 'Pending: fills at the next close', none: x.outcome.note }[x.outcome.status] || '')
const outcomeClass = (st) => ({ filled: 'text-ink-green-6', skipped: 'text-ink-amber-7', pending: 'text-ink-gray-6', none: 'text-ink-gray-6' }[st])

// Minimal, safe markdown for the agents' write-ups: escape first, then **bold**, headings and bullets.
const md = (t) => String(t || '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/^#{1,6}\s+(.*)$/gm, '<strong class="text-ink-gray-9">$1</strong>')
  .replace(/\*\*(.+?)\*\*/g, '<strong class="text-ink-gray-9">$1</strong>')
  .replace(/^\s*[-*]\s+/gm, '• ')
</script>
