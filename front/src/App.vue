<template>
  <header class="platform-shell">
    <strong>OTS 信息维护平台</strong>
    <span v-if="authentication.user">{{ authentication.user.display_name }}</span>
    <button v-if="authentication.user" type="button" @click="signOut">退出</button>
  </header>
  <p v-if="authentication.feedback" role="alert">{{ authentication.feedback }}</p>
  <RouterView />
</template>

<script setup lang="ts">
import { RouterView, useRouter } from 'vue-router'

import { logout } from './api/auth'
import { authentication, clearAuthentication } from './auth'

const router = useRouter()

async function signOut(): Promise<void> {
  try {
    await logout()
  } finally {
    clearAuthentication()
    await router.replace('/login')
  }
}
</script>
