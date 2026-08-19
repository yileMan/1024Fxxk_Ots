<template>
  <main class="health-page">
    <header>
      <p class="eyebrow">OPERATIONS / HEALTH</p>
      <h1>运行状态</h1>
      <p>实时确认 OTS 核心服务与数据连接是否处于可用状态。</p>
    </header>
    <section aria-labelledby="health-heading">
      <div class="section-heading"><span></span><h2 id="health-heading">系统健康</h2><small>LIVE CHECK</small></div>
      <div class="status-grid">
        <article><span class="status-dot" :class="serviceStatus === '可用' ? 'online' : 'offline'"></span><small>API SERVICE</small><strong>{{ serviceStatus }}</strong><p>服务状态：{{ serviceStatus }}</p></article>
        <article><span class="status-dot" :class="databaseStatus === '可用' ? 'online' : 'offline'"></span><small>DATABASE</small><strong>{{ databaseStatus }}</strong><p>数据库状态：{{ databaseStatus }}</p></article>
      </div>
      <p v-if="errorMessage" class="health-error" role="alert">{{ errorMessage }}</p>
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

<style scoped>
.health-page { max-width: 1180px; margin: 0 auto; padding: 72px 32px; }
header { padding-bottom: 44px; border-bottom: 1px solid var(--line); }
.eyebrow { margin: 0; color: var(--brand-red-deep); font-size: 11px; font-weight: 900; letter-spacing: .2em; }
h1 { margin: 12px 0; color: var(--ink); font: 700 clamp(46px, 7vw, 76px)/1 var(--font-display); letter-spacing: -.04em; }
header > p:last-child { max-width: 560px; color: var(--text-muted); line-height: 1.8; }
section { margin-top: 42px; }
.section-heading { display: flex; align-items: center; gap: 10px; }
.section-heading > span { width: 5px; height: 22px; background: var(--brand-red); }
.section-heading h2 { margin: 0; color: var(--ink); font-size: 19px; }
.section-heading small { margin-left: auto; color: var(--text-muted); font-size: 9px; letter-spacing: .16em; }
.status-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 22px; }
article { position: relative; min-height: 210px; padding: 28px; border: 1px solid var(--line); border-top: 3px solid var(--brand-red); border-radius: 5px; background: var(--paper); box-shadow: var(--shadow-card); }
article > small { display: block; color: var(--text-muted); font-size: 10px; font-weight: 800; letter-spacing: .18em; }
article > strong { display: block; margin-top: 34px; color: var(--ink); font-size: 34px; }
article > p { margin: 8px 0 0; color: var(--text-muted); font-size: 13px; }
.status-dot { position: absolute; top: 27px; right: 27px; width: 11px; height: 11px; border-radius: 50%; background: var(--line-strong); }
.status-dot.online { background: var(--success); box-shadow: 0 0 0 6px rgba(22, 132, 91, .1); }
.status-dot.offline { background: var(--danger); box-shadow: 0 0 0 6px rgba(180, 35, 42, .1); }
.health-error { margin-top: 18px; padding: 13px 16px; border-left: 4px solid var(--danger); background: #fff1f2; color: var(--danger); font-weight: 700; }
@media (max-width: 650px) { .health-page { padding: 48px 22px; } .status-grid { grid-template-columns: 1fr; } }
</style>
