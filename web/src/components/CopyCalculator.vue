<template>
  <section class="rounded-lg border border-outline-gray-2 p-4 space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-ink-gray-9">Thinking of copying {{ member.name }}?</h2>
      <p class="mt-1 text-sm text-ink-gray-6">
        This is what happened historically, not a recommendation. Copying means buying the day after a purchase
        was disclosed and holding six months.
      </p>
    </div>

    <div class="grid md:grid-cols-2 gap-3">
      <div class="rounded-lg bg-surface-gray-1 p-3">
        <div class="text-sm text-ink-gray-5">Historical odds a copied purchase beat SPY</div>
        <template v-if="co">
          <div class="mt-1 text-2xl font-semibold num text-ink-gray-9">{{ pct(co.odds, 0) }}</div>
          <div class="text-sm text-ink-gray-6 num">
            Likely range {{ pct(co.odds_range[0], 0) }}–{{ pct(co.odds_range[1], 0) }}, from {{ num(co.n) }} filings
            (raw record {{ pct(co.raw_rate, 0) }}, adjusted toward the {{ pct(base.hit_rate, 0) }} all-member rate for luck).
          </div>
        </template>
        <template v-else>
          <div class="mt-1 text-2xl font-semibold num text-ink-gray-9">{{ pct(base.hit_rate, 0) }}</div>
          <div class="text-sm text-ink-gray-6">No completed copied stock purchases for this member, so this is the all-member rate.</div>
        </template>
      </div>
      <div class="rounded-lg bg-surface-gray-1 p-3">
        <div class="text-sm text-ink-gray-5">Bad case for a copied stock purchase, 6 months</div>
        <div class="mt-1 text-2xl font-semibold num text-ink-red-6">{{ signedPct(pctls[tol.pctl], 0) }}</div>
        <div class="text-sm text-ink-gray-6">
          The {{ tol.badCase }} outcome{{ co && co.return_percentiles ? ' for this member\'s copied purchases' : ' across all copied purchases' }}.
          {{ pct(base.pct_lost_money, 0) }} of all copied purchases lost money.
        </div>
      </div>
    </div>

    <RiskSettings />

    <div>
      <div class="text-sm font-medium text-ink-gray-8">If you copy anyway, the most to put in:</div>
      <ul class="mt-2 divide-y divide-outline-gray-1">
        <li v-for="r in rows" :key="r.label" class="py-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span class="w-40 shrink-0 text-ink-gray-7">{{ r.label }}</span>
          <span class="text-xl font-semibold num text-ink-gray-9">{{ r.size.short }}</span>
          <span class="text-sm text-ink-gray-5 basis-full sm:basis-auto sm:flex-1">{{ r.size.reason }}</span>
        </li>
      </ul>
    </div>

    <p v-if="persist" class="text-sm text-ink-gray-5 leading-relaxed">
      <strong class="text-ink-gray-7">Do good odds last?</strong> Barely. Fitting these odds on trades before
      {{ persist.cut.slice(0, 4) }}, the members rated best ({{ pct(persist.top_third_predicted, 0) }}) beat SPY
      {{ pct(persist.top_third_realized, 0) }} of the time afterward, and the worst-rated
      {{ pct(persist.bottom_third_realized, 0) }}. That gap rests on {{ persist.members }} members and isn't
      statistically reliable (p = {{ persist.p_value.toFixed(2) }}).
    </p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import RiskSettings from './RiskSettings.vue'
import { risk, sizeTrade, TOLERANCES } from '../lib/risk'
import { num, pct, signedPct } from '../lib/format'

const props = defineProps({ member: { type: Object, required: true }, odds: { type: Object, required: true } })
const co = computed(() => props.member.copy_odds)
const base = computed(() => props.odds.stocks)
const persist = computed(() => props.odds.persistence)
const tol = computed(() => TOLERANCES[risk.tolerance] || TOLERANCES.moderate)
const pctls = computed(() => co.value?.return_percentiles || base.value.return_percentiles)
const rows = computed(() => [
  { label: 'A stock they buy', size: sizeTrade({ assetClass: 'Stock', percentiles: pctls.value }) },
  { label: 'An option they buy', size: sizeTrade({ assetClass: 'Options' }) },
  { label: 'An ETF they buy', size: sizeTrade({ assetClass: 'Funds & ETFs', percentiles: props.odds.etfs.return_percentiles }) },
])
</script>
