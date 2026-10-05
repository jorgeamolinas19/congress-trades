<template>
  <!-- frappe-ui charts fill their box; the box must have a height. -->
  <div class="h-80">
  <LineChart :key="theme" :title="title" :subtitle="subtitle" :data="rows" x="date" :y="keys"
    :series-config="config" :y-axis="{ format: (v) => `${v.toFixed(1)}x` }"
    class="h-full" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { LineChart } from 'frappe-ui/charts'
import { useTheme, seriesColors } from '../lib/theme'

// series: [{ key, label, color: 'trade'|'filing'|'spy', values }], dates: string[]
const props = defineProps({ title: String, subtitle: String, dates: Array, series: Array })
const { theme } = useTheme()

const keys = computed(() => props.series.map((s) => s.label))
const rows = computed(() =>
  props.dates.map((d, i) => Object.fromEntries([['date', d], ...props.series.map((s) => [s.label, s.values[i]])])),
)
const config = computed(() => {
  const c = seriesColors(theme.value)
  return Object.fromEntries(props.series.map((s) => [s.label, {
    color: c[s.color], dashed: s.color === 'spy', format: (v) => `${v.toFixed(2)}x`,
  }]))
})
</script>
