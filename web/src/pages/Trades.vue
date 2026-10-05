<template>
  <div class="space-y-5">
    <div>
      <h1 class="text-2xl font-semibold text-ink-gray-9">Latest disclosed trades</h1>
      <p class="mt-2 text-ink-gray-7">The 150 most recently disclosed stock trades<span v-if="s">, through {{ date(s.data_through) }}</span>.</p>
    </div>
    <div class="flex flex-wrap gap-3">
      <TabButtons v-model="side" :options="[{ label: 'All', value: 'all' }, { label: 'Buys', value: 'buy' }, { label: 'Sells', value: 'sell' }]" />
      <TextInput v-model="q" placeholder="Member or ticker…" class="w-full sm:w-56" aria-label="Filter trades" />
    </div>
    <div v-if="error" class="text-ink-red-6">{{ error }}</div>
    <div v-else-if="!s" class="text-ink-gray-5">Loading…</div>
    <div v-else class="overflow-x-auto rounded-lg border border-outline-gray-2">
      <table class="w-full text-base">
        <thead class="bg-surface-gray-1 text-sm text-ink-gray-6">
          <tr>
            <th class="px-3 py-2 text-left font-medium">Disclosed</th>
            <th class="px-3 py-2 text-left font-medium">Member</th>
            <th class="px-3 py-2 text-left font-medium">Stock</th>
            <th class="px-3 py-2 text-left font-medium">Type</th>
            <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Amount</th>
            <th class="px-3 py-2 text-left font-medium hidden md:table-cell">Traded</th>
            <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">Filing</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(t, i) in rows" :key="i" class="border-t border-outline-gray-1">
            <td class="px-3 py-2 whitespace-nowrap num">{{ date(t.filing_date) }}</td>
            <td class="px-3 py-2">
              <router-link :to="`/members/${t.member_id}`" class="font-medium hover:underline">{{ t.member }}</router-link>
              <div class="text-sm text-ink-gray-5">{{ memberTag(t) }}</div>
            </td>
            <td class="px-3 py-2"><span class="font-medium">{{ t.ticker }}</span>
              <div class="text-sm text-ink-gray-5 truncate max-w-[14rem]">{{ t.asset_name }}</div></td>
            <td class="px-3 py-2"><Badge :theme="t.side === 'buy' ? 'blue' : 'gray'" :label="t.side === 'buy' ? 'Buy' : 'Sell'" /></td>
            <td class="px-3 py-2 text-sm text-ink-gray-7 whitespace-nowrap hidden md:table-cell">{{ t.amount_raw }}</td>
            <td class="px-3 py-2 whitespace-nowrap num hidden md:table-cell">{{ date(t.tx_date) }}
              <span class="text-sm" :class="t.delay_days > 45 ? 'text-ink-amber-7' : 'text-ink-gray-5'">({{ t.delay_days }}d)</span></td>
            <td class="px-3 py-2 hidden lg:table-cell"><a :href="t.source_url" target="_blank" rel="noopener" class="text-sm text-ink-blue-link hover:underline">Original ↗</a></td>
          </tr>
          <tr v-if="!rows.length"><td colspan="7" class="px-3 py-6 text-center text-ink-gray-5">No trades match.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, TabButtons, TextInput } from 'frappe-ui'
import { getSummary } from '../lib/data'
import { date, memberTag } from '../lib/format'

const s = ref(null)
const error = ref('')
const side = ref('all')
const q = ref('')
onMounted(async () => { try { s.value = await getSummary() } catch (e) { error.value = e.message } })
const rows = computed(() => {
  const n = q.value.trim().toLowerCase()
  return (s.value?.recent || []).filter((t) => (side.value === 'all' || t.side === side.value) &&
    (!n || t.member.toLowerCase().includes(n) || t.ticker.toLowerCase() === n))
})
</script>
