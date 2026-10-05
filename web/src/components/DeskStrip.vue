<template>
  <div v-if="s" class="border-b border-outline-gray-2 bg-surface-gray-1 text-xs font-mono">
    <div class="mx-auto max-w-6xl px-4 h-7 flex items-center gap-4 text-ink-gray-5 uppercase tracking-wider overflow-hidden">
      <span class="whitespace-nowrap"><span class="text-ink-green-6">●</span> Filings through {{ fmt(s.data_through) }}</span>
      <span class="whitespace-nowrap hidden sm:inline">{{ num(s.study.sample.n_trades) }} stock trades</span>
      <span class="whitespace-nowrap hidden md:inline">{{ s.study.sample.n_members }} members</span>
      <span class="whitespace-nowrap hidden lg:inline">Factors through {{ fmt(s.factor_data_through) }}</span>
      <span class="whitespace-nowrap ml-auto hidden sm:inline">Updated daily · 07:30 ET</span>
    </div>
    <!-- Latest disclosures, scrolling. Duplicated once so the loop is seamless; pauses on hover. -->
    <div class="tape border-t border-outline-gray-1 h-7 flex items-center" aria-label="Latest disclosed trades">
      <div class="tape-track">
        <template v-for="k in 2" :key="k">
          <router-link v-for="(t, i) in tape" :key="`${k}-${i}`" :to="`/members/${t.member_id}`"
            class="inline-flex items-center gap-1.5 px-4 hover:text-ink-gray-9 text-ink-gray-6" :aria-hidden="k === 2">
            <span :class="t.side === 'buy' ? 'text-ink-green-6' : 'text-ink-red-6'">{{ t.side === 'buy' ? '▲ BUY' : '▼ SELL' }}</span>
            <span class="text-ink-gray-9 font-medium">{{ t.ticker }}</span>
            <span>{{ last(t.member) }}</span>
            <span class="text-ink-gray-5">{{ t.amount_raw.replace(/\$([\d,]+) - \$([\d,]+)/, (_, a, b) => `$${k_(a)}–${k_(b)}`) }}</span>
          </router-link>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSummary } from '../lib/data'
import { num } from '../lib/format'

const s = ref(null)
onMounted(() => getSummary().then((v) => { s.value = v }).catch(() => {}))
const tape = computed(() => (s.value?.recent || []).slice(0, 40))
const fmt = (d) => new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
const last = (name) => name.replace(/,.*$/, '').replace(/\s+(Jr\.?|Sr\.?|III|II|IV)$/, '').split(' ').pop()
const k_ = (x) => { const n = Number(x.replace(/,/g, '')); return n >= 1e6 ? `${(n / 1e6).toFixed(n % 1e6 ? 1 : 0)}M` : n >= 1000 ? `${Math.round(n / 1000)}K` : `${n}` }
</script>
