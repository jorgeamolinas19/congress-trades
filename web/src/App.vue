<template>
  <div class="min-h-screen flex flex-col overflow-x-clip">
    <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-2 focus:bg-surface-base focus:px-3 focus:py-2 focus:text-ink-gray-9 focus:shadow">Skip to content</a>

    <header class="sticky top-0 z-20 border-b border-outline-gray-2 bg-surface-base/95 backdrop-blur">
      <div class="mx-auto max-w-6xl px-4">
        <div class="h-14 flex items-center gap-3">
          <router-link to="/" class="flex items-center gap-2 font-semibold text-ink-gray-9 shrink-0" aria-label="Congress Trades Tracker home">
            <img src="/favicon.svg" alt="" class="h-6 w-6" />
            <span class="font-mono tracking-tight hidden lg:inline">CONGRESS<span class="text-ink-green-6">/</span>TRADES</span>
            <span class="font-mono tracking-tight lg:hidden">C<span class="text-ink-green-6">/</span>T</span>
          </router-link>

          <nav class="hidden md:flex items-center gap-0.5 ml-2" aria-label="Main">
            <router-link v-for="l in links" :key="l.to" :to="l.to" class="nav-link" :class="{ active: isActive(l) }">{{ l.label }}</router-link>
          </nav>

          <MemberSearch class="ml-auto hidden md:block w-64" />

          <!-- A plain link, not a router-link: a full page load is what makes the
               browser show the password prompt for the protected page. -->
          <a href="/picks" class="nav-link hidden md:inline-flex items-center gap-1" :class="{ active: route.name === 'picks' }"
            title="Private page, password required"><span aria-hidden="true">🔒</span> Picks</a>

          <Button variant="ghost" class="ml-auto md:ml-0" :tooltip="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
            :aria-label="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'" @click="toggle">
            <span aria-hidden="true">{{ theme === 'dark' ? '☀' : '☾' }}</span>
          </Button>
        </div>

        <!-- Phone: the search gets its own row and the sections scroll sideways. -->
        <div class="md:hidden pb-2 space-y-2">
          <MemberSearch class="w-full" :show-hint="false" />
          <nav class="flex gap-0.5 overflow-x-auto -mx-4 px-4 pb-1" aria-label="Main">
            <router-link v-for="l in links" :key="l.to" :to="l.to" class="nav-link whitespace-nowrap" :class="{ active: isActive(l) }">{{ l.label }}</router-link>
            <a href="/picks" class="nav-link whitespace-nowrap" :class="{ active: route.name === 'picks' }"><span aria-hidden="true">🔒</span> Picks</a>
          </nav>
        </div>
      </div>
    </header>
    <DeskStrip />

    <main id="main" class="flex-1 mx-auto w-full max-w-6xl px-4 py-6 md:py-8">
      <router-view />
    </main>

    <footer class="border-t border-outline-gray-2 text-sm text-ink-gray-5">
      <div class="mx-auto max-w-6xl px-4 py-6 grid gap-4 md:grid-cols-3">
        <div>
          <div class="font-medium text-ink-gray-7">Congress Trades Tracker</div>
          <p class="mt-1">Every disclosed stock trade by members of Congress since 2014, measured against the market.</p>
          <p v-if="dataThrough" class="mt-1">Filings through {{ date(dataThrough) }}. Updated daily before the US market opens.</p>
        </div>
        <div>
          <div class="font-medium text-ink-gray-7">Sources</div>
          <p class="mt-1">House Clerk and Senate eFD periodic transaction reports, yfinance prices, Ken French factor data.</p>
          <a class="underline hover:text-ink-gray-8" href="https://github.com/jorgeamolinas19/congress-trades" target="_blank" rel="noopener">Code and methodology on GitHub</a>
        </div>
        <div>
          <div class="font-medium text-ink-gray-7">Please note</div>
          <p class="mt-1">Historical patterns in public disclosure data. Not investment advice.</p>
          <p class="mt-1">Press <kbd class="rounded-2 border border-outline-gray-2 px-1 text-xs">/</kbd> to search members from any page.</p>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import MemberSearch from './components/MemberSearch.vue'
import DeskStrip from './components/DeskStrip.vue'
import { useTheme } from './lib/theme'
import { getSummary } from './lib/data'
import { date } from './lib/format'

const { theme, toggle } = useTheme()
const route = useRoute()
const links = [
  { to: '/', label: 'Overview', names: ['overview'] },
  { to: '/members', label: 'Members', names: ['members', 'member'] },
  { to: '/trades', label: 'Latest trades', names: ['trades'] },
  { to: '/other', label: 'Options & more', names: ['other'] },
]
const isActive = (l) => l.names.includes(route.name)
const dataThrough = ref(null)
onMounted(() => getSummary().then((s) => { dataThrough.value = s.data_through }).catch(() => {}))
</script>

<style scoped>
.nav-link {
  @apply px-2.5 py-1.5 rounded-2 font-mono text-sm tracking-wide text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9;
}
.nav-link.active {
  @apply bg-surface-gray-3 text-ink-gray-9;
}
</style>
