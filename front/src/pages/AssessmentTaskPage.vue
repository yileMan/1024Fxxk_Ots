<template>
  <main class="task-page">
    <header class="page-header">
      <div><p>ASSESSMENT QUEUE / LIVE</p><h1>{{ queueTitle }}</h1></div>
      <RouterLink to="/system">返回工作台</RouterLink>
    </header>

    <nav class="queue-tabs" aria-label="评估待办分类">
      <a v-for="item in queues" :key="item.value" :class="{ active: queue === item.value }" :href="`?queue=${item.value}&page=1`" @click.prevent="selectQueue(item.value)">{{ item.label }}</a>
    </nav>

    <p v-if="loading" class="state" aria-live="polite">正在读取当前分配…</p>
    <p v-else-if="error" class="state error" role="alert">{{ error }}</p>
    <section v-else-if="page?.items.length" class="task-list" aria-label="评估待办列表">
      <article v-for="task in page.items" :key="task.assessment_id">
        <div class="status-rail"><small>REV {{ task.revision_no }}</small><strong>{{ labels[task.status] }}</strong></div>
        <div class="task-main">
          <div class="task-heading"><h2>{{ task.cve_id }}</h2><span :class="`severity ${task.source_severity?.toLowerCase() ?? 'none'}`">{{ task.source_severity ?? '来源未提供' }}</span></div>
          <p>{{ task.product_name }} {{ task.version_no }}</p>
          <p class="ots">{{ task.ots_name }} {{ task.ots_version }}</p>
        </div>
        <div class="task-actions">
          <RouterLink :to="`/system/vulnerabilities/${task.vulnerability_id}`" class="detail-link">漏洞事实</RouterLink>
          <RouterLink :to="`/system/assessments/${task.assessment_id}?from=${task.status}`" class="detail-link" data-action="open-assessment">{{ task.status === 'submitted' ? '查看评估' : '填写评估' }} ↗</RouterLink>
        </div>
      </article>
    </section>
    <section v-else-if="page" class="state empty" data-state="empty"><h2>当前队列为空</h2><p>没有符合当前身份、状态和产品范围的任务。</p></section>
    <nav v-if="page && page.total > page.page_size" class="pagination" aria-label="评估待办分页">
      <button :disabled="page.page <= 1" @click="goToPage(page.page - 1)">上一页</button>
      <span>第 {{ page.page }} / {{ Math.ceil(page.total / page.page_size) }} 页</span>
      <button :disabled="page.page * page.page_size >= page.total" @click="goToPage(page.page + 1)">下一页</button>
    </nav>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { CatalogApiError, getAssessmentTasks, type AssessmentQueue, type AssessmentTaskPage } from '../api/vulnerabilityCatalog'

const queues: { value: AssessmentQueue; label: string }[] = [
  { value: 'pending', label: '待产品评估' },
  { value: 'reassess', label: '待复评' },
  { value: 'returned', label: '已退回' },
  { value: 'submitted', label: '待审核' },
]
const labels: Record<string, string> = Object.fromEntries(queues.map(item => [item.value, item.label]))
const initial = new URL(window.location.href).searchParams
const rawQueue = initial.get('queue')
const queue = ref<AssessmentQueue>(queues.some(item => item.value === rawQueue) ? rawQueue as AssessmentQueue : 'pending')
const currentPage = ref(Math.max(1, Number(initial.get('page')) || 1))
const page = ref<AssessmentTaskPage | null>(null)
const loading = ref(true)
const error = ref('')
const queueTitle = computed(() => labels[queue.value])

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    page.value = await getAssessmentTasks({ queue: queue.value, page: currentPage.value, pageSize: 20 })
  } catch (reason) {
    page.value = null
    error.value = reason instanceof CatalogApiError && reason.status === 403
      ? '无权查看该待办队列，产品授权或人员分配可能已变化。'
      : '待办暂时不可用，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function selectQueue(value: AssessmentQueue): void {
  queue.value = value
  currentPage.value = 1
  updateUrl()
  void load()
}

function goToPage(value: number): void {
  currentPage.value = value
  updateUrl()
  void load()
}

function updateUrl(): void {
  const url = new URL(window.location.href)
  url.searchParams.set('queue', queue.value)
  url.searchParams.set('page', String(currentPage.value))
  window.history.pushState({}, '', url)
}
</script>

<style scoped>
.task-page{max-width:1180px;margin:0 auto;padding:52px 32px 80px}.page-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.page-header p{margin:0;color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.18em}.page-header h1{margin:10px 0 0;color:var(--ink);font:750 clamp(40px,6vw,68px)/1 var(--font-display)}.page-header a,.detail-link{border-bottom:2px solid var(--brand-red);padding:8px 0;text-decoration:none;font-size:12px;font-weight:900}.queue-tabs{display:flex;gap:0;margin-top:38px;border-bottom:1px solid var(--line-strong)}.queue-tabs a{padding:13px 18px;text-decoration:none;font-size:12px;font-weight:800}.queue-tabs a.active{color:#fff;background:var(--ink)}.state{margin-top:24px;padding:22px;border:1px solid var(--line-strong);background:#fff}.state.error{border-left:5px solid var(--brand-red)}.empty h2{margin:0;color:var(--ink)}.task-list{display:grid;gap:10px;margin-top:18px}.task-list article{display:grid;grid-template-columns:135px 1fr auto;align-items:center;gap:24px;min-height:126px;border:1px solid var(--line);background:#fff;box-shadow:0 8px 24px rgba(32,36,40,.05)}.status-rail{align-self:stretch;display:flex;flex-direction:column;justify-content:center;padding:20px;border-left:5px solid var(--brand-red);background:var(--paper-warm)}.status-rail small{color:var(--text-muted);font:700 10px Consolas,monospace}.status-rail strong{margin-top:8px;color:var(--ink)}.task-main h2{margin:0;color:var(--ink);font:750 24px var(--font-display)}.task-main p{margin:9px 0 0}.task-main .ots{color:var(--text-muted);font-size:13px}.task-heading{display:flex;align-items:center;gap:12px}.severity{padding:4px 7px;border:1px solid var(--line-strong);font-size:10px;font-weight:900}.severity.high,.severity.critical{color:var(--brand-red);border-color:#e7a3a7}.detail-link{margin-right:24px}.pagination{display:flex;align-items:center;justify-content:center;gap:18px;margin-top:22px}.pagination button{border:1px solid var(--line-strong);padding:8px 14px;background:#fff;cursor:pointer}.pagination button:disabled{cursor:not-allowed;opacity:.45}@media(max-width:760px){.task-page{padding:32px 16px}.page-header{align-items:flex-start;flex-direction:column}.queue-tabs{overflow:auto}.task-list article{grid-template-columns:1fr;gap:0}.detail-link{margin:0 20px 20px}.status-rail{border-left:0;border-top:5px solid var(--brand-red)}}
</style>
