<template>
  <div class="min-h-screen flex flex-col overflow-x-clip">
    <header class="min-w-0 border-b border-outline-gray-2 bg-surface-base sticky top-0 z-20">
      <div class="mx-auto max-w-6xl px-4 h-14 flex items-center gap-4">
        <router-link to="/" class="flex items-center gap-2 font-semibold text-ink-gray-9 shrink-0">
          <img src="/favicon.svg" alt="" class="h-6 w-6" />
          <span class="hidden sm:inline">Congress Trades Tracker</span>
        </router-link>
        <nav class="flex min-w-0 items-center gap-1 overflow-x-auto">
          <router-link v-for="l in links" :key="l.to" :to="l.to"
            class="px-2.5 py-1.5 rounded text-base text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 whitespace-nowrap"
            active-class="!bg-surface-gray-3 !text-ink-gray-9" :exact-active-class="l.exact ? '!bg-surface-gray-3 !text-ink-gray-9' : ''">
            {{ l.label }}
          </router-link>
        </nav>
        <div class="ml-auto">
          <Button variant="ghost" :tooltip="theme === 'dark' ? 'Light mode' : 'Dark mode'" @click="toggle"
            :aria-label="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'">
            <span aria-hidden="true">{{ theme === 'dark' ? '☀' : '☾' }}</span>
          </Button>
        </div>
      </div>
    </header>
    <main class="flex-1 mx-auto w-full max-w-6xl px-4 py-8">
      <router-view />
    </main>
    <footer class="border-t border-outline-gray-2 text-sm text-ink-gray-5">
      <div class="mx-auto max-w-6xl px-4 py-6 flex flex-wrap gap-x-6 gap-y-2">
        <span>Data: House Clerk &amp; Senate eFD periodic transaction reports, yfinance, Ken French Data Library.</span>
        <span>Not investment advice.</span>
        <a class="underline hover:text-ink-gray-8" href="https://github.com/jorgeamolinas19/congress-trades" target="_blank" rel="noopener">Source on GitHub</a>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import { useTheme } from './lib/theme'

const { theme, toggle } = useTheme()
const links = [
  { to: '/', label: 'Overview', exact: true },
  { to: '/members', label: 'Members' },
  { to: '/trades', label: 'Latest trades' },
]
</script>
