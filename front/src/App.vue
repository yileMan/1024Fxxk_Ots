<template>
  <header class="platform-shell">
    <strong>OTS 信息维护平台</strong>
    <span v-if="authentication.user">{{ authentication.user.display_name }}</span>
  </header>
  <p v-if="authentication.feedback" role="alert">{{ authentication.feedback }}</p>
  <RouterView />
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'

import { authentication } from './auth'
</script>
