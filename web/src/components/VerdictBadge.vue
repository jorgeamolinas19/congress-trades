<template>
  <Badge :theme="v.theme" :variant="v.variant" :size="size" :label="v.label" />
</template>

<script setup>
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import { VERDICTS } from '../lib/format'

const props = defineProps({ verdict: { type: String, required: true }, size: { type: String, default: 'md' } })
const v = computed(() => VERDICTS[props.verdict] || VERDICTS.insufficient)
</script>
