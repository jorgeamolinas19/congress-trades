<template>
  <div class="rounded-lg border border-dashed border-outline-gray-3 px-4 py-10 text-center">
    <div class="text-base font-medium text-ink-gray-8">{{ title }}</div>
    <p v-if="hint" class="mt-1 text-sm text-ink-gray-5">{{ hint }}</p>
    <div v-if="$slots.default" class="mt-3 flex justify-center gap-2"><slot /></div>
  </div>
</template>

<script setup>
defineProps({ title: { type: String, required: true }, hint: String })
</script>
