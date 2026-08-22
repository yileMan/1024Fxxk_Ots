<template>
  <main class="collector-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">DATA EXCHANGE / COLLECTOR SCOPE</p>
        <h1>采集范围</h1>
        <span>从当前启用产品版本实时生成最小 OTS 范围，供外部数据服务离线采集。</span>
      </div>
      <div class="heading-actions">
        <button data-action="refresh" :disabled="loading" @click="load">
          {{ loading ? '正在刷新…' : '刷新范围' }}
        </button>
        <button class="primary" data-action="download" :disabled="loading || downloading" @click="download">
          {{ downloading ? '正在生成…' : '下载 collector_scope.csv' }}
        </button>
      </div>
    </header>

    <p v-if="loadError" class="error-panel" role="alert">
      <strong>采集范围暂时不可用</strong>
      <span>没有展示上一次结果，请检查服务后重试。</span>
    </p>
    <p v-if="downloadError" class="error-panel compact" role="alert">下载失败，请稍后重试。</p>
    <p v-if="downloadEvidence" class="success-panel" aria-live="polite">
      <strong>导出完成</strong>
      <span>导出 ID {{ downloadEvidence.scopeExportId.slice(0, 8) }} · SHA-256 {{ downloadEvidence.sha256.slice(0, 12) }}…</span>
    </p>

    <section v-if="loading && !preview" class="loading-state" aria-live="polite">
      <span class="pulse" aria-hidden="true"></span>
      正在计算当前范围与覆盖位置…
    </section>

    <template v-else-if="preview">
      <section class="scope-summary" aria-label="采集范围摘要">
        <article class="scope-total">
          <small>当前最小范围</small>
          <strong>{{ preview.scope_count }} <span>个 OTS</span></strong>
          <p>同一 OTS 被多个产品版本使用时仅出现一次。</p>
        </article>
        <article class="baseline-card">
          <small>比较基线</small>
          <template v-if="preview.comparison_baseline.available">
            <strong>{{ preview.comparison_baseline.batch_no }}</strong>
            <p>最近成功批次 · {{ formatTime(preview.comparison_baseline.finished_at) }}</p>
          </template>
          <template v-else>
            <strong>尚无成功批次可供比较</strong>
            <p>当前范围不会被误报为全量新增。</p>
          </template>
        </article>
        <article class="change-card added">
          <small>范围变化</small>
          <strong>新增 {{ preview.changes.added_count }}</strong>
          <p>{{ idSummary(preview.changes.added_ots_ids) }}</p>
        </article>
        <article class="change-card removed">
          <small>范围变化</small>
          <strong>移除 {{ preview.changes.removed_count }}</strong>
          <p>{{ idSummary(preview.changes.removed_ots_ids) }}</p>
        </article>
      </section>

      <section v-if="preview.items.length === 0" class="empty-state">
        <span aria-hidden="true">Ø</span>
        <div><h2>当前没有需要采集的 OTS</h2><p>启用产品版本并建立 OTS 关联后，下一次刷新会自动进入范围。</p></div>
      </section>

      <section v-else class="scope-table-wrap">
        <div class="table-title">
          <div><small>LIVE SCOPE</small><h2>范围明细</h2></div>
          <p>覆盖时间只由该 OTS 最近一次成功结果推进。</p>
        </div>
        <div class="table-scroll">
          <table>
            <thead><tr><th>ID</th><th>OTS</th><th>版本</th><th>官方网站</th><th>数据覆盖位置</th></tr></thead>
            <tbody>
              <tr v-for="item in preview.items" :key="item.ots_id">
                <td class="mono">{{ item.ots_id }}</td>
                <td><strong>{{ item.ots_name }}</strong></td>
                <td class="mono">{{ item.ots_version }}</td>
                <td><a :href="item.official_website" target="_blank" rel="noopener noreferrer">{{ item.official_website }}</a></td>
                <td>
                  <span v-if="item.is_initial_collection" class="coverage initial">首次采集</span>
                  <span v-else class="coverage covered">{{ formatTime(item.last_covered_time) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  downloadCollectorScope,
  getCollectorScope,
  type CollectorScopeDownloadEvidence,
  type CollectorScopePreview,
} from '../api/collectorScope'

const preview = ref<CollectorScopePreview | null>(null)
const loading = ref(true)
const downloading = ref(false)
const loadError = ref(false)
const downloadError = ref(false)
const downloadEvidence = ref<CollectorScopeDownloadEvidence | null>(null)

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  loadError.value = false
  preview.value = null
  try {
    preview.value = await getCollectorScope()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function download(): Promise<void> {
  if (downloading.value) return
  downloading.value = true
  downloadError.value = false
  downloadEvidence.value = null
  try {
    downloadEvidence.value = await downloadCollectorScope()
    await load()
  } catch {
    downloadError.value = true
  } finally {
    downloading.value = false
  }
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    hour12: false,
  }).format(new Date(value))
}

function idSummary(ids: number[]): string {
  if (ids.length === 0) return '本次没有变化'
  const shown = ids.slice(0, 5).join('、')
  return ids.length > 5 ? `OTS ID ${shown} 等` : `OTS ID ${shown}`
}
</script>

<style scoped>
.collector-page{max-width:1320px;margin:0 auto;padding:48px 32px 72px}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:32px}.eyebrow{margin:0;color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.18em}.page-heading h1{margin:9px 0 10px;color:var(--ink);font:750 clamp(42px,6vw,68px)/.95 var(--font-display);letter-spacing:-.045em}.page-heading span{color:var(--text-muted);line-height:1.7}.heading-actions{display:flex;gap:10px;flex:0 0 auto}button{min-height:44px;padding:9px 15px;border:1px solid var(--line-strong);color:var(--ink);background:#fff;font:700 12px var(--font-body);cursor:pointer}button:hover:not(:disabled){border-color:var(--brand-red);color:var(--brand-red-deep)}button:disabled{opacity:.55;cursor:wait}.primary{border-color:var(--brand-red);color:#fff;background:var(--brand-red);box-shadow:0 9px 20px rgba(215,25,32,.18)}.primary:hover:not(:disabled){color:#fff;background:var(--brand-red-deep)}.scope-summary{display:grid;grid-template-columns:1.25fr 1.25fr .8fr .8fr;gap:12px;margin:36px 0 18px}.scope-summary article{min-height:174px;padding:23px;border:1px solid var(--line-strong);background:#fff;box-shadow:0 8px 24px rgba(32,36,40,.05)}.scope-summary small,.table-title small{color:var(--text-muted);font-size:10px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}.scope-summary strong{display:block;margin-top:25px;color:var(--ink);font:750 25px/1.15 var(--font-display)}.scope-total{position:relative;overflow:hidden;background:var(--ink)!important}.scope-total:after{position:absolute;right:-25px;bottom:-52px;width:145px;height:145px;border:18px solid var(--brand-red);border-radius:50%;content:"";opacity:.84}.scope-total small,.scope-total strong,.scope-total p{position:relative;z-index:1;color:#fff}.scope-total strong{font-size:46px}.scope-total strong span{font-size:16px}.scope-summary p{margin:12px 0 0;color:var(--text-muted);font-size:12px;line-height:1.55}.scope-total p{max-width:230px;color:rgba(255,255,255,.62)}.change-card{border-top-width:4px!important}.change-card.added{border-top-color:#16845b}.change-card.removed{border-top-color:var(--brand-red)}.change-card strong{font-size:22px}.scope-table-wrap,.empty-state,.loading-state{border:1px solid var(--line-strong);background:#fff;box-shadow:var(--shadow-card)}.table-title{display:flex;align-items:flex-end;justify-content:space-between;padding:24px 26px;border-bottom:1px solid var(--line)}.table-title h2{margin:4px 0 0;color:var(--ink);font:750 25px var(--font-display)}.table-title p{margin:0;color:var(--text-muted);font-size:12px}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:17px 20px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--text-muted);background:var(--paper-warm);font-size:10px;letter-spacing:.1em}td{font-size:13px}tbody tr:hover{background:#fffafa}td strong{color:var(--ink)}td a{display:inline-block;max-width:340px;overflow:hidden;color:var(--brand-red-deep);text-overflow:ellipsis;vertical-align:middle;white-space:nowrap}.mono{font-family:Consolas,"Cascadia Mono",monospace}.coverage{display:inline-flex;align-items:center;gap:7px;font-weight:800}.coverage:before{width:7px;height:7px;border-radius:50%;content:""}.coverage.initial{color:#9a6510}.coverage.initial:before{background:#d99a2b}.coverage.covered{color:#167054}.coverage.covered:before{background:#16845b}.empty-state{display:flex;align-items:center;gap:25px;padding:44px}.empty-state>span{display:grid;place-items:center;width:72px;height:72px;border:2px solid var(--line-strong);border-radius:50%;color:var(--brand-red);font:700 28px var(--font-display)}.empty-state h2{margin:0;color:var(--ink)}.empty-state p{margin-bottom:0;color:var(--text-muted)}.loading-state{display:flex;align-items:center;gap:14px;margin-top:36px;padding:30px;color:var(--text-muted)}.pulse{width:12px;height:12px;border-radius:50%;background:var(--brand-red);animation:pulse 1.1s ease-in-out infinite}.error-panel,.success-panel{display:flex;gap:8px;margin:24px 0 0;padding:15px 18px;border-left:4px solid var(--brand-red);background:#fff1f2;color:var(--brand-red-deep);font-size:13px}.error-panel{flex-direction:column}.error-panel.compact{display:block}.success-panel{border-color:#16845b;background:#edf9f4;color:#126348}.success-panel span{color:#397663}@keyframes pulse{50%{transform:scale(.55);opacity:.35}}@media(max-width:980px){.scope-summary{grid-template-columns:1fr 1fr}.page-heading{align-items:stretch;flex-direction:column}.heading-actions{align-self:flex-start}}@media(max-width:640px){.collector-page{padding:28px 14px 48px}.scope-summary{grid-template-columns:1fr}.heading-actions{width:100%;flex-direction:column}.table-title{align-items:flex-start;flex-direction:column;gap:8px}.empty-state{align-items:flex-start;padding:28px 20px}}@media(prefers-reduced-motion:reduce){.pulse{animation:none}}
</style>
