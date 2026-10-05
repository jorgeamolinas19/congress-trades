<template>
  <div class="space-y-6">
    <PageHeader title="Options, bonds, funds and other assets">
      Everything members disclosed that isn't common stock. These trades are listed as filed but are
      <strong>not part of the performance analysis</strong>: free price history doesn't exist for individual option
      contracts or most bonds. Funds and ETFs show a 6-month return vs SPY where they can be priced.
    </PageHeader>

    <ErrorState v-if="error" :message="error" />
    <div v-else-if="!rows || !s" class="space-y-6" aria-busy="true">
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3"><Skeleton v-for="i in 5" :key="i" class="h-24 rounded-lg" /></div>
      <TableSkeleton :rows="8" :cols="6" />
    </div>
    <template v-else>
      <section class="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <button v-for="c in classes" :key="c" class="text-left rounded-lg border p-4 transition-colors"
          :class="cls === c ? 'border-outline-gray-5 bg-surface-gray-1' : 'border-outline-gray-2 hover:bg-surface-gray-1'"
          :aria-pressed="cls === c" @click="cls = cls === c ? 'all' : c">
          <div class="text-sm text-ink-gray-5">{{ c }}</div>
          <div class="mt-1 text-2xl font-semibold num text-ink-gray-9">{{ num(s.other.counts[c] || 0) }}</div>
          <div class="mt-1 text-sm text-ink-gray-6">{{ cls === c ? 'Showing only these' : 'disclosed trades' }}</div>
        </button>
      </section>

      <section class="rounded-lg border border-outline-gray-2 p-4 max-w-3xl">
        <div class="text-sm font-medium text-ink-gray-8">Most active options traders</div>
        <ul class="mt-2 grid sm:grid-cols-2 gap-x-6">
          <li v-for="m in s.other.top_option_traders" :key="m.member_id" class="py-1.5 flex items-center gap-2 border-b border-outline-gray-1">
            <router-link :to="`/members/${m.member_id}#other`" class="font-medium text-ink-gray-9 hover:underline truncate">{{ m.member }}</router-link>
            <span class="text-sm text-ink-gray-5 whitespace-nowrap">{{ memberTag(m) }}</span>
            <span class="ml-auto num text-ink-gray-7">{{ num(m.n) }}</span>
          </li>
        </ul>
      </section>

      <RiskSettings />

      <OtherTradesTable :key="cls" :trades="rows" :odds="s.odds" show-member :initial-class="cls" />
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Skeleton } from 'frappe-ui'
import PageHeader from '../components/PageHeader.vue'
import OtherTradesTable from '../components/OtherTradesTable.vue'
import RiskSettings from '../components/RiskSettings.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import ErrorState from '../components/ErrorState.vue'
import { getOther, getSummary } from '../lib/data'
import { memberTag, num } from '../lib/format'

const route = useRoute()
const router = useRouter()
const classes = ['Options', 'Bonds & Treasuries', 'Funds & ETFs', 'Crypto', 'Private & other']
const cls = ref(classes.includes(route.query.class) ? route.query.class : 'all')
watch(cls, (v) => router.replace({ query: v === 'all' ? {} : { class: v } }))
const rows = ref(null)
const s = ref(null)
const error = ref('')
onMounted(async () => {
  try { [rows.value, s.value] = await Promise.all([getOther(), getSummary()]) } catch (e) { error.value = e.message }
})
</script>
