<template>
  <!-- Full alert on the overview; a one-line, expandable note elsewhere so it
       stays visible without crowding out the page's own content. -->
  <Alert v-if="!compact" theme="blue" title="Options, bonds, funds and ETFs"
    description="Only common stock is analyzed. Some well-known traders (Nancy Pelosi's household, for example) trade mainly through options, so the performance figures cover only part of their activity.">
    <template #actions>
      <Button route="/other" label="See options, bonds &amp; funds trades →" />
    </template>
  </Alert>
  <div v-else class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7">
    <span class="text-ink-blue-6" aria-hidden="true">ⓘ</span>
    Performance figures cover common stock only; options, bonds and funds are listed separately.
    <button class="text-ink-blue-link hover:underline ml-1" :aria-expanded="openMore" @click="openMore = !openMore">
      {{ openMore ? 'Less' : 'Why that matters' }}
    </button>
    <p v-if="openMore" class="mt-2 text-ink-gray-6">
      Only common stock is analyzed. Some well-known traders (Nancy Pelosi's household, for example) trade mainly
      through options, so the performance figures cover only part of their activity.
      <router-link to="/other" class="text-ink-blue-link hover:underline">See options, bonds &amp; funds trades →</router-link>
    </p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Alert, Button } from 'frappe-ui'

defineProps({ compact: { type: Boolean, default: false } })
const openMore = ref(false)
</script>
