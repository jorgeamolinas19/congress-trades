<template>
  <div class="max-w-xl mx-auto py-12 text-center space-y-5">
    <div class="text-6xl font-semibold text-ink-gray-3 num font-mono">404</div>
    <h1 class="text-2xl font-semibold text-ink-gray-9">That page doesn't exist</h1>
    <p class="text-ink-gray-6">If you were looking for a member, try the search below.</p>
    <MemberSearch class="mx-auto max-w-sm text-left" size="md" :show-hint="false" autofocus />
    <div class="flex justify-center gap-2 pt-2">
      <Button route="/" label="Overview" />
      <Button route="/members" label="All members" />
      <Button route="/trades" label="Latest trades" />
    </div>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import MemberSearch from '../components/MemberSearch.vue'
</script>
