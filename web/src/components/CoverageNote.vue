<template>
  <Alert theme="blue" title="Options, bonds, funds and ETFs"
    description="Only common stock is analyzed. Some well-known traders (Nancy Pelosi's household, for example) trade mainly through options, so the performance figures cover only part of their activity.">
    <template #actions>
      <Button route="/other" label="See options, bonds &amp; funds trades →" />
    </template>
  </Alert>
</template>

<script setup>
import { Alert, Button } from 'frappe-ui'
</script>
