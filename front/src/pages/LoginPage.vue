<template>
  <main>
    <h1>登录 OTS 信息维护平台</h1>
    <p v-if="authentication.feedback" role="alert">{{ authentication.feedback }}</p>
    <form @submit.prevent="submit">
      <label>
        登录名
        <input v-model="loginName" name="login_name" autocomplete="username" required />
      </label>
      <label>
        密码
        <input v-model="password" name="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
      <button type="submit" :disabled="submitting">{{ submitting ? '正在登录…' : '登录' }}</button>
    </form>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { AuthenticationError, login } from '../api/auth'
import { authentication, setAuthenticatedUser } from '../auth'

const route = useRoute()
const router = useRouter()
const loginName = ref('')
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)

async function submit(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const user = await login(loginName.value, password.value)
    setAuthenticatedUser(user)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/system'
    await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/system')
  } catch (error) {
    errorMessage.value = error instanceof AuthenticationError && error.code === 'AUTH_INVALID_CREDENTIALS'
      ? '账号或密码错误'
      : '登录服务暂时不可用'
  } finally {
    submitting.value = false
  }
}
</script>
