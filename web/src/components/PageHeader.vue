<template>
  <div class="flex flex-wrap items-end justify-between gap-4">
    <div class="max-w-3xl min-w-0">
      <Breadcrumbs v-if="crumbs" :items="crumbs" class="mb-2" />
      <h1 class="text-2xl font-semibold tracking-tight text-ink-gray-9">{{ title }}</h1>
      <p v-if="description || $slots.default" class="mt-2 text-ink-gray-7 leading-relaxed"><slot>{{ description }}</slot></p>
    </div>
    <div v-if="$slots.actions" class="flex items-center gap-2 shrink-0"><slot name="actions" /></div>
  </div>
</template>

<script setup>
import { Breadcrumbs } from 'frappe-ui'

defineProps({ title: { type: String, required: true }, description: String, crumbs: Array })
</script>
