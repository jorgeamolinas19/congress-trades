<template>
  <div class="rounded-lg border border-outline-gray-2 overflow-hidden" role="status" aria-live="polite">
    <div class="bg-surface-gray-1 px-3 py-2.5 flex gap-6">
      <Skeleton v-for="c in cols" :key="c" class="h-3 rounded-2" :class="c === 1 ? 'w-40' : 'w-16'" />
    </div>
    <div v-for="r in rows" :key="r" class="border-t border-outline-gray-1 px-3 py-3 flex items-center gap-6">
      <div class="w-40 space-y-1.5"><Skeleton class="h-3.5 w-32 rounded-2" /><Skeleton class="h-2.5 w-20 rounded-2" /></div>
      <Skeleton v-for="c in cols - 1" :key="c" class="h-3.5 w-14 rounded-2" />
    </div>
    <span class="sr-only">Loading</span>
  </div>
</template>

<script setup>
import { Skeleton } from 'frappe-ui'

defineProps({ rows: { type: Number, default: 8 }, cols: { type: Number, default: 5 } })
</script>
