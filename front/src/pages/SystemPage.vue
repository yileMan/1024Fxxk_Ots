<template>
  <main class="system-page">
    <p class="eyebrow">CONTROL DESK / OVERVIEW</p>
    <h1>系统工作台</h1>
    <p class="intro">按当前身份、人员分配和产品范围实时计算。这里的数量就是站内待办，不依赖通知同步。</p>
    <p v-if="loading" class="live-state" aria-live="polite">正在读取实时待办…</p>
    <p v-else-if="error" class="live-state error" role="alert">工作台实时数据暂时不可用，请稍后重试。</p>
    <section v-else-if="summary" class="task-grid" aria-label="当前用户实时待办">
      <RouterLink v-for="card in taskCards" :key="card.queue" class="task-card" :to="`/system/assessments/tasks?queue=${card.queue}&page=1`">
        <small>{{ card.kicker }}</small><h2>{{ card.label }}<strong>{{ card.count }}</strong></h2><p>{{ card.note }}</p><b>进入已过滤列表 ↗</b>
      </RouterLink>
    </section>
    <section v-if="isAdmin && importSummary" class="import-strip" aria-label="最近导入与覆盖摘要">
      <div><small>最近成功导入</small><strong>{{ importSummary.latest_succeeded?.batch_no ?? '暂无成功批次' }}</strong><span>{{ formatTime(importSummary.last_successful_import_at) }}</span></div>
      <div><small>最近失败批次</small><strong>{{ importSummary.latest_failed?.batch_no ?? '暂无失败批次' }}</strong><span>{{ importSummary.latest_failed?.error_code ?? '无失败摘要' }}</span></div>
      <div><small>数据状态</small><strong>覆盖截止时间{{ importSummary.last_covered_time ? formatTime(importSummary.last_covered_time) : '未提供' }}</strong><span v-if="!importSummary.last_covered_time">NVD 来源窗口不作为逐 OTS 覆盖时间</span></div>
    </section>
    <div class="module-grid">
      <RouterLink v-if="isAdmin" class="module-card featured" to="/system/products">
        <span>01</span><small>主数据</small><h2>产品管理</h2><p>维护产品、版本、负责人、审核人和版本 OTS 清单。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="hasScopedProducts" class="module-card featured" to="/system/my-products">
        <span>01</span><small>授权范围</small><h2>我的产品</h2><p>只读查看已授权产品、版本和对应 OTS 清单。</p><b>查看产品 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card" to="/system/ots">
        <span>02</span><small>共享组件</small><h2>OTS 主数据</h2><p>维护 OTS 名称、版本、官方网站、EOL 与关联产品。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card" to="/system/users">
        <span>03</span><small>系统管理</small><h2>用户与角色</h2><p>维护账号、固定角色、密码与人员状态。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card exchange" to="/system/data-exchange/collector-scope">
        <span>04</span><small>离线数据交换</small><h2>采集范围</h2><p>预览实际在用 OTS、覆盖位置和范围变化，下载规范 CSV。</p><b>生成范围 ↗</b>
      </RouterLink>
      <RouterLink class="module-card" to="/health">
        <span>05</span><small>平台运行</small><h2>服务状态</h2><p>检查 API 与数据库可用性。</p><b>查看状态 ↗</b>
      </RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { authentication } from '../auth'
import { getImportSummary, getWorkbenchSummary, type ImportSummary, type WorkbenchSummary } from '../api/vulnerabilityCatalog'

const isAdmin = computed(() => authentication.user?.roles.includes('admin') ?? false)
const hasScopedProducts = computed(() => !isAdmin.value && (authentication.scope?.effective_product_ids.length ?? 0) > 0)
const summary = ref<WorkbenchSummary | null>(null)
const importSummary = ref<ImportSummary | null>(null)
const loading = ref(true)
const error = ref(false)
const taskCards = computed(() => summary.value ? [
  { queue: 'pending', kicker: 'OWNER / NEW', label: '待产品评估', count: summary.value.pending_count, note: '当前负责人名下的新任务' },
  { queue: 'reassess', kicker: 'OWNER / CHANGE', label: '待复评', count: summary.value.reassess_count, note: '来源或候选变化后的当前修订' },
  { queue: 'returned', kicker: 'OWNER / RETURN', label: '已退回', count: summary.value.returned_count, note: '需要重新确认的退回记录' },
  { queue: 'submitted', kicker: 'REVIEWER / READY', label: '待审核', count: summary.value.submitted_count, note: '当前指定审核人的已提交记录' },
] : [])

onMounted(async () => {
  try {
    summary.value = await getWorkbenchSummary()
    if (isAdmin.value) importSummary.value = await getImportSummary()
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})

function formatTime(value: string | null): string { return value ? new Date(value).toLocaleString('zh-CN') : '未提供' }
</script>

<style scoped>
.system-page { max-width: 1180px; margin: 0 auto; padding: 72px 32px; }
.eyebrow { color: var(--amber-dark); font-size: 11px; font-weight: 900; letter-spacing: .2em; }
h1 { margin: 12px 0; color: var(--ink); font: 700 clamp(46px, 7vw, 76px)/1 var(--font-display); letter-spacing: -.04em; }
.intro { max-width: 600px; color: var(--text-muted); line-height: 1.8; }
.live-state{margin:28px 0 0;padding:14px 18px;border-left:4px solid var(--line-strong);background:#fff}.live-state.error{border-left-color:var(--brand-red)}
.task-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:32px}.task-card{position:relative;min-height:180px;padding:22px;border:1px solid var(--line-strong);background:#fff;color:var(--ink);text-decoration:none;overflow:hidden}.task-card::after{content:"";position:absolute;right:-26px;bottom:-36px;width:110px;height:110px;border:18px solid var(--paper-warm);transform:rotate(18deg)}.task-card small{color:var(--brand-red);font-size:9px;font-weight:900;letter-spacing:.12em}.task-card h2{display:flex;align-items:end;justify-content:space-between;gap:10px;margin:28px 0 8px;font-size:17px}.task-card h2 strong{color:var(--brand-red);font:750 46px/1 var(--font-display)}.task-card p{position:relative;z-index:1;color:var(--text-muted);font-size:11px}.task-card b{position:absolute;bottom:18px;left:22px;z-index:1;color:var(--ink);font-size:10px}.import-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:10px;background:var(--line-strong);border:1px solid var(--line-strong)}.import-strip>div{display:flex;min-height:96px;flex-direction:column;justify-content:center;padding:18px;background:var(--ink);color:#fff}.import-strip small{color:rgba(255,255,255,.48);font-size:9px;font-weight:900;letter-spacing:.1em}.import-strip strong{margin-top:8px}.import-strip span{margin-top:5px;color:rgba(255,255,255,.55);font-size:10px}
.module-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-top: 50px; }
.module-card { min-height: 280px; padding: 30px; border: 1px solid var(--line-strong); background: var(--paper); color: var(--ink); text-decoration: none; box-shadow: var(--shadow-card); transition: transform .2s; }
.module-card:hover { transform: translateY(-4px); }
.module-card.featured { color: var(--paper); background: var(--forest); }
.module-card.exchange { border-top: 4px solid var(--brand-red); }
.module-card > span { float: right; color: var(--amber); font: 700 44px var(--font-display); }
.module-card small { color: var(--amber-dark); font-weight: 900; letter-spacing: .15em; }
.featured small { color: var(--amber); }
.featured > span, .featured small, .featured b { color: #fff; opacity: .82; }
.module-card h2 { margin: 44px 0 12px; font: 700 32px var(--font-display); }
.module-card p { max-width: 330px; line-height: 1.7; opacity: .72; }
.module-card b { display: inline-block; margin-top: 28px; color: var(--amber); font-size: 12px; }
@media (max-width: 900px) { .task-grid { grid-template-columns:repeat(2,1fr) }.import-strip{grid-template-columns:1fr} }
@media (max-width: 650px) { .module-grid,.task-grid { grid-template-columns: 1fr; } }
</style>
