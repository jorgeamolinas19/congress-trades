<template>
  <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3">
    <div class="flex flex-wrap items-end gap-3">
      <label class="flex flex-col gap-1 text-sm text-ink-gray-6">
        Portfolio
        <TextInput type="number" :model-value="risk.portfolio" class="w-32" aria-label="Portfolio amount in dollars"
          @update:model-value="(v) => (risk.portfolio = Math.max(0, Number(v) || 0))" />
      </label>
      <label class="flex flex-col gap-1 text-sm text-ink-gray-6">
        Most I'll lose on one trade
        <Select v-model="risk.maxLossPct" :options="lossOptions" class="w-40" aria-label="Maximum loss per trade" />
      </label>
      <div class="flex flex-col gap-1 text-sm text-ink-gray-6">
        Risk tolerance
        <TabButtons v-model="risk.tolerance" :options="tolOptions" />
      </div>
    </div>
    <p class="mt-2 text-sm text-ink-gray-6">
      On any single copied trade you're willing to lose up to
      <strong class="text-ink-gray-9 num">{{ money(lossBudget()) }}</strong>
      ({{ risk.maxLossPct }}% of {{ money(Number(risk.portfolio) || 0) }}). {{ TOLERANCES[risk.tolerance].label }} sizing plans for the
      {{ TOLERANCES[risk.tolerance].badCase }} historical outcome and caps any one position at
      {{ Math.round(TOLERANCES[risk.tolerance].cap * 100) }}% of the portfolio.
    </p>
  </div>
</template>

<script setup>
import { Select, TabButtons, TextInput } from 'frappe-ui'
import { lossBudget, risk, TOLERANCES } from '../lib/risk'
import { usd as money } from '../lib/format'

const lossOptions = [1, 2, 3, 5, 10].map((v) => ({ label: `${v}% of portfolio`, value: v }))
const tolOptions = Object.entries(TOLERANCES).map(([value, t]) => ({ label: t.label, value }))
</script>
