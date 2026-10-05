<template>
  <div>
    <div class="flex flex-wrap items-center gap-3">
      <TabButtons v-model="cls" :options="classOptions" />
      <TabButtons v-model="side" :options="[{ label: 'All', value: 'all' }, { label: 'Buys', value: 'buy' }, { label: 'Sells', value: 'sell' }]" />
      <TextInput v-model="q" :placeholder="showMember ? 'Member or ticker…' : 'Ticker or name…'" class="w-full sm:w-52" aria-label="Filter" />
      <span class="text-sm text-ink-gray-5 sm:ml-auto">{{ num(filtered.length) }} trades</span>
    </div>
    <div class="mt-3 overflow-x-auto rounded-lg border border-outline-gray-2">
      <table class="w-full text-base">
        <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
          <tr>
            <th class="px-3 py-2 text-left font-medium">Traded</th>
            <th v-if="showMember" class="px-3 py-2 text-left font-medium">Member</th>
            <th class="px-3 py-2 text-left font-medium">Asset</th>
            <th class="px-3 py-2 text-left font-medium">Details</th>
            <th class="px-3 py-2 text-left font-medium">Type</th>
            <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Amount</th>
            <th class="px-3 py-2 text-right font-medium hidden md:table-cell" title="Funds and ETFs only">6 mo vs SPY</th>
            <th v-if="odds" class="px-3 py-2 text-right font-medium hidden md:table-cell" title="Based on your risk settings">Max to put in</th>
            <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">Filing</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(t, i) in page" :key="i" class="border-t border-outline-gray-1 align-top">
            <td class="px-3 py-2 whitespace-nowrap num">{{ date(t.tx_date) }}
              <div class="text-xs text-ink-gray-5">filed {{ t.delay_days }}d later</div></td>
            <td v-if="showMember" class="px-3 py-2">
              <router-link :to="`/members/${t.member_id}`" class="font-medium hover:underline">{{ t.member }}</router-link>
              <div class="text-sm text-ink-gray-5">{{ memberTag(t) }}</div>
            </td>
            <td class="px-3 py-2 max-w-[16rem]">
              <span v-if="t.ticker" class="font-medium">{{ t.ticker }}</span>
              <div class="text-sm text-ink-gray-6 truncate">{{ t.asset_name || '—' }}</div>
              <Badge class="mt-1" theme="gray" size="sm" :label="t.asset_class" />
            </td>
            <td class="px-3 py-2 text-sm text-ink-gray-7 max-w-[18rem]">
              <span v-if="optionSummary(t)" class="font-medium text-ink-gray-8">{{ optionSummary(t) }}</span>
              <div v-if="t.detail" class="text-ink-gray-5 line-clamp-2">{{ t.detail }}</div>
              <span v-if="!optionSummary(t) && !t.detail" class="text-ink-gray-4">—</span>
            </td>
            <td class="px-3 py-2"><Badge :theme="t.side === 'buy' ? 'blue' : 'gray'" :label="t.side === 'buy' ? 'Buy' : 'Sell'" />
              <div v-if="t.owner && t.owner !== 'Self'" class="text-xs text-ink-gray-5 mt-0.5">{{ t.owner }}</div></td>
            <td class="px-3 py-2 text-sm text-ink-gray-7 whitespace-nowrap hidden md:table-cell">{{ t.amount_raw }}</td>
            <td class="px-3 py-2 text-right num whitespace-nowrap hidden md:table-cell" :class="excessClass(t.excess_6m)">
              <template v-if="t.excess_6m !== null && t.excess_6m !== undefined">{{ signedPct(t.excess_6m) }}<span v-if="!t.complete" class="text-xs text-ink-gray-5"> so far</span></template>
              <span v-else class="text-ink-gray-4">—</span>
            </td>
            <td v-if="odds" class="px-3 py-2 text-right num whitespace-nowrap hidden md:table-cell" :title="size(t).reason">{{ size(t).short }}</td>
            <td class="px-3 py-2 hidden lg:table-cell">
              <a :href="t.source_url" target="_blank" rel="noopener" class="text-sm text-ink-blue-link hover:underline">Original ↗</a>
            </td>
          </tr>
          <tr v-if="!page.length"><td colspan="9" class="px-3 py-6 text-center text-ink-gray-5">No trades match.</td></tr>
        </tbody>
      </table>
    </div>
    <div v-if="pages > 1" class="mt-3 flex items-center gap-2">
      <Button :disabled="p === 0" label="Previous" @click="p--" />
      <span class="text-sm text-ink-gray-6">Page {{ p + 1 }} of {{ num(pages) }}</span>
      <Button :disabled="p >= pages - 1" label="Next" @click="p++" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Badge, Button, TabButtons, TextInput } from 'frappe-ui'
import { date, excessClass, memberTag, num, signedPct } from '../lib/format'
import { sizeTrade } from '../lib/risk'

const props = defineProps({
  trades: { type: Array, required: true },
  showMember: { type: Boolean, default: false },
  initialClass: { type: String, default: 'all' },
  odds: { type: Object, default: null },
})
const CLASSES = ['Options', 'Bonds & Treasuries', 'Funds & ETFs', 'Crypto', 'Private & other']
const cls = ref(props.initialClass)
const side = ref('all')
const q = ref('')
const p = ref(0)
const PER_PAGE = 50

// Only offer the classes this list actually contains.
const classOptions = computed(() => [{ label: 'All', value: 'all' },
  ...CLASSES.filter((c) => props.trades.some((t) => t.asset_class === c)).map((c) => ({ label: c, value: c }))])

const filtered = computed(() => {
  const n = q.value.trim().toLowerCase()
  return props.trades.filter((t) => (cls.value === 'all' || t.asset_class === cls.value) &&
    (side.value === 'all' || t.side === side.value) &&
    (!n || (t.ticker || '').toLowerCase() === n || (t.asset_name || '').toLowerCase().includes(n) ||
      (props.showMember && (t.member || '').toLowerCase().includes(n))))
})
watch([cls, side, q, () => props.trades], () => { p.value = 0 })
const pages = computed(() => Math.ceil(filtered.value.length / PER_PAGE))
const page = computed(() => filtered.value.slice(p.value * PER_PAGE, (p.value + 1) * PER_PAGE))

const size = (t) => sizeTrade({ assetClass: t.asset_class, side: t.side, percentiles: props.odds?.etfs.return_percentiles })

function optionSummary(t) {
  if (t.asset_class !== 'Options') return ''
  const parts = [t.option_type, t.strike ? `$${t.strike.toLocaleString('en-US')} strike` : null,
    t.expiry ? `exp ${t.expiry}` : null, t.contracts ? `${num(t.contracts)} contracts` : null].filter(Boolean)
  return parts.join(' · ')
}
</script>
