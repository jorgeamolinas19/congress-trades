<template>
  <div class="rounded-2 border border-outline-gray-2 bg-surface-gray-1 p-4">
    <div class="eyebrow text-ink-gray-5">{{ label }}</div>
    <div class="mt-1.5 text-2xl font-semibold num" :class="valueClass">{{ value }}</div>
    <div v-if="sub" class="mt-1 text-sm text-ink-gray-6">{{ sub }}</div>
  </div>
</template>

<script setup>
defineProps({ label: String, value: [String, Number], sub: String, valueClass: { type: String, default: 'text-ink-gray-9' } })
</script>
