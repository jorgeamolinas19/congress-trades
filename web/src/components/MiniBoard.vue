<template>
  <ul class="divide-y divide-outline-gray-1">
    <li v-for="m in members" :key="m.id" class="py-2 flex items-center gap-3">
      <div class="min-w-0">
        <router-link :to="`/members/${m.id}`" class="font-medium text-ink-gray-9 hover:underline truncate block">{{ m.name }}</router-link>
        <div class="text-sm text-ink-gray-5">{{ memberTag(m) }} · {{ m.n_buys }} buys</div>
      </div>
      <div class="ml-auto text-right shrink-0">
        <div class="num font-medium" :class="excessClass(m.trade.excess_ann)">{{ signedPct(m.trade.excess_ann) }} / yr</div>
        <div class="text-sm text-ink-gray-5 num">vs SPY · t = {{ tstat(m.trade.alpha_t) }}</div>
      </div>
    </li>
  </ul>
</template>

<script setup>
import { excessClass, memberTag, signedPct, tstat } from '../lib/format'

defineProps({ members: { type: Array, required: true } })
</script>
