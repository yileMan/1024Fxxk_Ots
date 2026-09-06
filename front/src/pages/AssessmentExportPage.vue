<template>
  <main class="export-page">
    <header><p>DATA EXCHANGE / ASSESSMENT EXPORT</p><h1>评估导出</h1><span>选择产品版本与 OTS，导出当前完整评估表。</span></header>
    <section class="panel">
      <div class="fields">
        <label>产品版本<select data-field="version" v-model.number="versionId" :disabled="loading" @change="versionChanged"><option :value="0">请选择</option><option v-for="item in versions" :key="item.id" :value="item.id">{{ item.productName }} / {{ item.versionNo }}</option></select></label>
        <label>OTS<select data-field="ots" v-model.number="otsId" :disabled="!versionId || loadingOts"><option :value="0">请选择</option><option v-for="item in otsItems" :key="item.ots_component_id" :value="item.ots_component_id">{{ item.ots_name }} / {{ item.ots_version }}</option></select></label>
      </div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <button data-action="preview" :disabled="!versionId || !otsId || previewing" @click="loadPreview">{{ previewing ? '正在预检…' : '预检导出范围' }}</button>
    </section>
    <section v-if="preview" class="confirm">
      <small>EXPORT SNAPSHOT</small><h2>{{ preview.product_name }} / {{ preview.version_no }}</h2>
      <p>{{ preview.ots_name }} {{ preview.ots_version }} · <strong>{{ preview.row_count }} 条当前评估</strong></p>
      <p>数量为预检时快照，下载以实际请求开始时的数据为准。</p>
      <div class="actions">
        <button v-if="downloading" @click="cancelDownload">取消下载</button>
        <button class="primary" data-action="download" :disabled="preview.row_count === 0 || downloading" @click="download">{{ downloading ? '下载中…' : '确认并下载 CSV' }}</button>
      </div>
    </section>
    <p v-if="completed" class="success" aria-live="polite">导出完成：{{ completed }}</p>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { downloadAssessmentExport, previewAssessmentExport, type AssessmentExportPreview } from '../api/assessmentExport'
import { listProductOts, type ProductOts } from '../api/ots'
import { listProducts, listVersions } from '../api/products'

type VersionOption = { id: number; productName: string; versionNo: string }
const versions = ref<VersionOption[]>([]), otsItems = ref<ProductOts[]>([])
const versionId = ref(0), otsId = ref(0)
const loading = ref(true), loadingOts = ref(false), previewing = ref(false), downloading = ref(false)
const preview = ref<AssessmentExportPreview | null>(null), error = ref(''), completed = ref('')
let controller: AbortController | null = null

onMounted(async () => {
  try {
    const products = await listProducts({ status: 'active', pageSize: 100 })
    const groups = await Promise.all(products.items.map(async product => ({ product, versions: await listVersions(product.id) })))
    versions.value = groups.flatMap(({ product, versions: items }) => items.filter(item => item.status === 'active').map(item => ({ id: item.id, productName: product.product_name, versionNo: item.version_no })))
  } catch { error.value = '产品版本加载失败，请重试' } finally { loading.value = false }
})

async function versionChanged(): Promise<void> {
  otsId.value = 0; otsItems.value = []; preview.value = null; completed.value = ''; error.value = ''
  if (!versionId.value) return
  loadingOts.value = true
  try { otsItems.value = await listProductOts(versionId.value) } catch { error.value = 'OTS 范围加载失败，请重试' } finally { loadingOts.value = false }
}
async function loadPreview(): Promise<void> {
  previewing.value = true; preview.value = null; completed.value = ''; error.value = ''
  try { preview.value = await previewAssessmentExport(versionId.value, otsId.value) } catch { error.value = '导出预检失败，可能无权访问或范围已变化' } finally { previewing.value = false }
}
async function download(): Promise<void> {
  if (downloading.value) return
  downloading.value = true; completed.value = ''; error.value = ''; controller = new AbortController()
  try { completed.value = await downloadAssessmentExport(versionId.value, otsId.value, controller.signal) } catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) error.value = '下载失败，请重新预检后重试' } finally { downloading.value = false; controller = null }
}
function cancelDownload(): void { controller?.abort() }
</script>

<style scoped>
.export-page{max-width:1050px;margin:0 auto;padding:48px 32px}.export-page header p,.confirm small{color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.16em}.export-page h1{margin:8px 0;color:var(--ink);font:750 58px/1 var(--font-display)}header span{color:var(--text-muted)}.panel,.confirm{margin-top:32px;padding:28px;border:1px solid var(--line-strong);background:#fff;box-shadow:var(--shadow-card)}.fields{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:20px}label{display:grid;gap:8px;color:var(--ink);font-weight:700}select{min-height:44px;padding:0 12px;border:1px solid var(--line-strong);background:#fff}button{min-height:42px;padding:0 16px;border:1px solid var(--line-strong);background:#fff;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}.primary{border-color:var(--brand-red);color:#fff;background:var(--brand-red)}.confirm h2{margin:8px 0}.confirm p{color:var(--text-muted)}.actions{display:flex;justify-content:flex-end;gap:10px}.error{color:var(--danger)}.success{padding:14px 18px;border-left:4px solid var(--success);background:#edf9f4;color:#126348}@media(max-width:650px){.export-page{padding:28px 14px}.fields{grid-template-columns:1fr}.export-page h1{font-size:42px}}
</style>
