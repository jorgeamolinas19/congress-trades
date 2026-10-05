<template>
  <div class="space-y-6">
    <div class="max-w-3xl">
      <h1 class="text-2xl font-semibold text-ink-gray-9">Options, bonds, funds and other assets</h1>
      <p class="mt-2 text-ink-gray-7 leading-relaxed">
        Trades in everything other than common stock: stock options, Treasuries and bonds, funds and ETFs,
        crypto, and private holdings. They are listed as disclosed but are <strong>not part of the performance
        analysis</strong>, because free price history doesn't exist for individual option contracts or most bonds.
        Funds and ETFs show their 6-month return vs SPY where it can be priced.
      </p>
    </div>

    <div v-if="error" class="text-ink-red-6">{{ error }}</div>
    <div v-else-if="!rows || !s" class="text-ink-gray-5">Loading…</div>
    <template v-else>
      <section class="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatTile v-for="c in classes" :key="c" :label="c" :value="num(s.other.counts[c] || 0)" sub="disclosed trades" />
      </section>

      <section class="rounded-lg border border-outline-gray-2 p-4 max-w-3xl">
        <div class="text-sm font-medium text-ink-gray-8">Most active options traders</div>
        <ul class="mt-2 grid sm:grid-cols-2 gap-x-6">
          <li v-for="m in s.other.top_option_traders" :key="m.member_id" class="py-1.5 flex items-center gap-2 border-b border-outline-gray-1">
            <router-link :to="`/members/${m.member_id}`" class="font-medium text-ink-gray-9 hover:underline truncate">{{ m.member }}</router-link>
            <span class="text-sm text-ink-gray-5 whitespace-nowrap">{{ memberTag(m) }}</span>
            <span class="ml-auto num text-ink-gray-7">{{ num(m.n) }}</span>
          </li>
        </ul>
      </section>

      <OtherTradesTable :trades="rows" show-member :initial-class="$route.query.class || 'all'" />
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import StatTile from '../components/StatTile.vue'
import OtherTradesTable from '../components/OtherTradesTable.vue'
import { getOther, getSummary } from '../lib/data'
import { memberTag, num } from '../lib/format'

const classes = ['Options', 'Bonds & Treasuries', 'Funds & ETFs', 'Crypto', 'Private & other']
const rows = ref(null)
const s = ref(null)
const error = ref('')
onMounted(async () => {
  try { [rows.value, s.value] = await Promise.all([getOther(), getSummary()]) } catch (e) { error.value = e.message }
})
</script>
