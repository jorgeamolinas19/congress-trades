<template>
  <div class="rounded-lg border border-outline-red-3 bg-surface-red-1 px-4 py-4" role="alert">
    <div class="font-medium text-ink-red-7">Couldn't load this page</div>
    <p class="mt-1 text-sm text-ink-red-6">{{ message }}</p>
    <div class="mt-3 flex gap-2">
      <Button label="Try again" @click="reload" />
      <Button variant="ghost" route="/" label="Go to overview" />
    </div>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'

defineProps({ message: { type: String, default: 'Something went wrong while fetching the data.' } })
const reload = () => window.location.reload()
</script>
