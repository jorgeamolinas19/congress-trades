<template>
  <!-- frappe-ui charts fill their box; the box must have a height. -->
  <div class="h-80">
  <LineChart :key="theme" :title="title" :subtitle="subtitle" :data="rows" x="date" :y="keys"
    :series-config="config" :y-axis="{ format: axisFmt, ...(yMin !== undefined && { min: yMin }) }"
    class="h-full" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { LineChart } from 'frappe-ui/charts'
import { useTheme, seriesColors } from '../lib/theme'

// series: [{ label, color: 'trade'|'filing'|'spy'|'stats', values }], dates: string[]
// unit 'x' formats growth multiples (1.50x); 'usd' formats dollar values ($1,050).
const props = defineProps({ title: String, subtitle: String, dates: Array, series: Array,
  unit: { type: String, default: 'x' }, yMin: Number })
const { theme } = useTheme()

const axisFmt = (v) => (props.unit === 'usd' ? `$${Math.round(v).toLocaleString('en-US')}` : `${v.toFixed(1)}x`)
const valueFmt = (v) => (props.unit === 'usd' ? `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : `${v.toFixed(2)}x`)

const keys = computed(() => props.series.map((s) => s.label))
const rows = computed(() =>
  props.dates.map((d, i) => Object.fromEntries([['date', d], ...props.series.map((s) => [s.label, s.values[i]])])),
)
const config = computed(() => {
  const c = seriesColors(theme.value)
  return Object.fromEntries(props.series.map((s) => [s.label, {
    color: c[s.color], dashed: s.color === 'spy', format: valueFmt,
  }]))
})
</script>
