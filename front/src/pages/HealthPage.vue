<template>
  <main class="platform-shell">
    <header>
      <h1>OTS 信息维护平台</h1>
      <p>平台基础服务状态</p>
    </header>
    <section aria-labelledby="health-heading">
      <h2 id="health-heading">系统健康</h2>
      <p>服务状态：{{ serviceStatus }}</p>
      <p>数据库状态：{{ databaseStatus }}</p>
      <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

type HealthResponse = { service: string; database: string }

const serviceStatus = ref('加载中')
const databaseStatus = ref('加载中')
const errorMessage = ref('')

onMounted(async () => {
  try {
    const response = await fetch('/api/v1/health')
    const payload = (await response.json()) as HealthResponse
    if (!response.ok) throw new Error('health unavailable')
    serviceStatus.value = payload.service === 'available' ? '可用' : '不可用'
    databaseStatus.value = payload.database === 'available' ? '可用' : '不可用'
  } catch {
    serviceStatus.value = '不可用'
    databaseStatus.value = '不可用'
    errorMessage.value = '无法连接系统健康服务'
  }
})
</script>
