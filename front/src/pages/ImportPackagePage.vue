<template>
  <main class="package-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">DATA EXCHANGE / NVD FACT INTAKE</p>
        <h1>数据包导入</h1>
        <span>先导入 NVD 漏洞事实和受影响软件范围；内部 OTS 匹配由后续流程执行。</span>
      </div>
      <div class="contract-seal" aria-label="当前数据包格式版本">
        <small>CONTRACT</small><strong>1.0</strong><span>2 CSV / ZIP</span>
      </div>
    </header>

    <ol class="step-rail" aria-label="数据包导入步骤">
      <li data-step="upload" :class="{ active: !result }"><span>01</span><div><strong>上传数据包</strong><small>选择两文件 ZIP</small></div></li>
      <li data-step="validate" :class="{ active: result?.status === 'validated' || result?.status === 'failed' }"><span>02</span><div><strong>校验预览</strong><small>与漏洞库真实比较</small></div></li>
      <li data-step="confirm" :class="{ active: result?.status === 'validated' }" :aria-disabled="result?.status === 'validated' ? undefined : 'true'"><span>03</span><div><strong>确认导入</strong><small>事务写入漏洞事实</small></div></li>
      <li data-step="result" :class="{ active: result?.status === 'succeeded' }" :aria-disabled="result?.status === 'succeeded' ? undefined : 'true'"><span>04</span><div><strong>查看结果</strong><small>等待内部 OTS 匹配</small></div></li>
    </ol>

    <section class="upload-gate">
      <div class="gate-copy">
        <small>CONTROLLED INTAKE</small>
        <h2>NVD 漏洞事实入口</h2>
        <p>文件只在内网受控目录处理；校验和导入不会访问互联网，也不会提前生成 OTS 候选关系或产品任务。</p>
        <ul><li>固定两文件根目录</li><li>一行一个 CVE</li><li>不包含内部 OTS ID</li></ul>
      </div>
      <div class="file-control">
        <label for="package-file">选择数据包</label>
        <div class="file-picker" :class="{ selected: selectedFile }">
          <input id="package-file" type="file" accept=".zip,application/zip" :disabled="submitting || confirming" @change="selectFile">
          <span class="file-icon" aria-hidden="true">ZIP</span>
          <div><strong>{{ selectedFile?.name ?? '拖入或选择规范 ZIP' }}</strong><small>{{ selectedFile ? formatBytes(selectedFile.size) : 'ots_intelligence_YYYYMMDD_HHMMSS.zip · 最大 50 MiB' }}</small></div>
        </div>
        <button class="primary" data-action="validate" :disabled="!selectedFile || !!selectionError || submitting || confirming" @click="validateSelected">
          {{ submitting ? '正在上传并校验…' : '上传并开始校验' }}
        </button>
      </div>
    </section>

    <p v-if="selectionError" class="feedback error" role="alert">{{ selectionError }}</p>
    <p v-if="requestError" class="feedback error" role="alert"><strong>{{ requestError }}</strong><span>页面不会显示或复用过期结果，请重新校验。</span></p>
    <p v-if="downloadError" class="feedback error" role="alert">错误清单下载失败，请稍后重试。</p>
    <p v-if="downloadedFile" class="feedback success" aria-live="polite">已下载 {{ downloadedFile }}</p>
    <p v-if="submitting || confirming" class="validating" aria-live="polite"><i></i><span><strong>{{ confirming ? '正在事务导入漏洞事实' : '正在执行受限校验' }}</strong>{{ confirming ? '确认阶段会重新比较数据库，任一失败都将整批回滚。' : '依次检查 ZIP、manifest、CSV、JSON、摘要和数据库差异。' }}</span></p>

    <template v-if="result">
      <section class="result-banner" :class="result.status">
        <div>
          <small>{{ bannerTag }}</small>
          <h2>{{ bannerTitle }}</h2>
          <p>批次 {{ result.batch_no }} · {{ result.source_name?.toUpperCase() ?? 'UNKNOWN' }} · 格式 {{ result.format_version }}</p>
        </div>
        <span class="status-mark" aria-hidden="true">{{ result.status === 'failed' ? '!' : '✓' }}</span>
      </section>

      <section v-if="result.source_release" class="source-strip" aria-label="来源信息">
        <div><small>来源发布</small><strong>{{ result.source_release }}</strong></div>
        <div><small>来源窗口</small><strong>{{ result.window_start }} → {{ result.window_end }}</strong></div>
        <div><small>分类依据</small><strong>{{ result.classification_basis }}</strong></div>
      </section>

      <section class="metrics" aria-label="分类统计">
        <article><small>全部 CVE</small><strong>{{ result.summary.total }}</strong></article>
        <article class="new"><small>新增</small><strong>{{ result.summary.new }}</strong></article>
        <article><small>更新</small><strong>{{ result.summary.update }}</strong></article>
        <article><small>重复</small><strong>{{ result.summary.duplicate }}</strong></article>
        <article class="conflict"><small>冲突</small><strong>{{ result.summary.conflict }}</strong></article>
        <article class="error"><small>错误</small><strong>{{ result.summary.error }}</strong></article>
      </section>

      <section v-if="samples.length" class="sample-ledger">
        <div class="section-heading"><div><small>CVE PREVIEW</small><h2>漏洞事实样例</h2></div><p>仅展示有界样例，完整内容将在确认后写入漏洞库。</p></div>
        <article v-for="sample in samples" :key="String(sample.cve_id)" class="sample-card">
          <div><strong class="mono">{{ sample.cve_id }}</strong><span>{{ sample.vuln_status }}</span></div>
          <p>{{ sample.description }}</p>
          <dl><div><dt>受影响软件/版本</dt><dd>{{ formatAffected(sample) }}</dd></div><div><dt>CVSS v3.1</dt><dd>{{ formatScore(sample) }}</dd></div></dl>
        </article>
      </section>

      <section class="evidence-grid">
        <article class="file-ledger">
          <div class="section-heading"><div><small>FILE LEDGER</small><h2>文件级证据</h2></div><p>manifest + nvd_cves.csv</p></div>
          <div class="table-scroll"><table><thead><tr><th>文件</th><th>总计</th><th>新增</th><th>更新</th><th>重复</th><th>冲突</th><th>错误</th></tr></thead><tbody><tr v-for="[name, stats] in fileEntries" :key="name"><td class="mono"><strong>{{ name }}</strong></td><td>{{ stats.total }}</td><td>{{ stats.new }}</td><td>{{ stats.update }}</td><td>{{ stats.duplicate }}</td><td>{{ stats.conflict }}</td><td>{{ stats.error }}</td></tr></tbody></table></div>
        </article>

        <aside v-if="result.status === 'validated'" class="write-action">
          <small>TRANSACTION BOUNDARY</small><h2>只写入漏洞事实</h2>
          <p>将新增/更新第 8 张表。不会生成 OTS 候选关系或产品评估任务。</p>
          <button data-action="confirm" :disabled="confirming || !result.can_import" @click="confirmSelected">{{ confirming ? '正在导入…' : '确认导入漏洞事实' }}</button>
        </aside>
        <aside v-else-if="result.status === 'succeeded'" class="write-action succeeded-panel">
          <small>IMPORT SUCCEEDED</small><h2>漏洞事实已成功导入</h2>
          <p>内部 OTS 匹配尚未执行。后续由 OTS-08 使用受影响软件和版本范围生成候选关系。</p>
        </aside>
      </section>

      <section v-if="result.status === 'failed'" class="error-ledger">
        <div class="section-heading"><div><small>REJECTION LEDGER</small><h2>错误清单</h2></div><button data-action="download-errors" :disabled="downloading" @click="downloadErrors">{{ downloading ? '正在下载…' : '下载错误清单 CSV' }}</button></div>
        <p v-if="result.truncated_error_count" class="truncated">另有 {{ result.truncated_error_count }} 项未在页面展示。</p>
        <div class="table-scroll"><table><thead><tr><th>文件</th><th>位置</th><th>字段</th><th>错误码</th><th>原因</th><th>拒绝值</th></tr></thead><tbody><tr v-for="(error, index) in result.errors" :key="`${error.file_name}-${error.row_number}-${index}`"><td class="mono">{{ error.file_name }}</td><td>{{ error.row_number ? `第 ${error.row_number} 行` : '文件级' }}</td><td class="mono">{{ error.field ?? '—' }}</td><td class="mono code">{{ error.error_code }}</td><td>{{ error.reason }}</td><td class="rejected">{{ error.rejected_value ?? '—' }}</td></tr></tbody></table></div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  confirmImportPackage,
  downloadPackageErrors,
  getImportPackage,
  validateImportPackage,
  type ImportPackageResult,
} from '../api/importPackages'

const MAX_FILE_BYTES = 50 * 1024 * 1024
const PACKAGE_NAME = /^ots_intelligence_\d{8}_\d{6}\.zip$/
const selectedFile = ref<File | null>(null)
const selectionError = ref('')
const requestError = ref('')
const downloadError = ref(false)
const downloadedFile = ref('')
const submitting = ref(false)
const confirming = ref(false)
const downloading = ref(false)
const result = ref<ImportPackageResult | null>(null)

const fileEntries = computed(() => Object.entries(result.value?.file_stats ?? {}).filter(([, stats]) => stats.total > 0 || stats.error > 0))
const samples = computed<Record<string, unknown>[]>(() => fileEntries.value.flatMap(([, stats]) => stats.samples as Record<string, unknown>[]))
const bannerTitle = computed(() => {
  if (result.value?.status === 'succeeded') return '漏洞事实已成功导入'
  if (result.value?.status === 'validated') return '校验通过，可以导入漏洞事实'
  return '校验未通过'
})
const bannerTag = computed(() => {
  if (result.value?.status === 'succeeded') return 'SUCCEEDED / FACTS COMMITTED'
  if (result.value?.status === 'validated') return 'VALIDATED / CONFIRM REQUIRED'
  return 'FAILED / ACTION REQUIRED'
})

onMounted(async () => {
  const batchId = Number(new URL(window.location.href).searchParams.get('batch'))
  if (!Number.isInteger(batchId) || batchId <= 0) return
  submitting.value = true
  try { result.value = await getImportPackage(batchId) }
  catch { requestError.value = '批次加载失败' }
  finally { submitting.value = false }
})

function selectFile(event: Event): void {
  result.value = null
  requestError.value = ''
  downloadError.value = false
  downloadedFile.value = ''
  selectionError.value = ''
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  selectedFile.value = file
  if (!file) return
  if (!PACKAGE_NAME.test(file.name)) selectionError.value = '仅支持 ZIP 数据包，文件名必须为 ots_intelligence_YYYYMMDD_HHMMSS.zip。'
  else if (file.size > MAX_FILE_BYTES) selectionError.value = '数据包不能超过 50 MiB。'
}

async function validateSelected(): Promise<void> {
  if (!selectedFile.value || selectionError.value || submitting.value) return
  const file = selectedFile.value
  result.value = null
  requestError.value = ''
  submitting.value = true
  try {
    result.value = await validateImportPackage(file)
    const url = new URL(window.location.href)
    url.searchParams.set('batch', String(result.value.id))
    window.history.replaceState({}, '', url)
  } catch { requestError.value = '上传或校验失败' }
  finally { submitting.value = false }
}

async function confirmSelected(): Promise<void> {
  if (!result.value || result.value.status !== 'validated' || confirming.value) return
  if (!window.confirm(`确认导入批次 ${result.value.batch_no} 的漏洞事实？该操作不会执行内部 OTS 匹配。`)) return
  confirming.value = true
  requestError.value = ''
  try { result.value = await confirmImportPackage(result.value.id) }
  catch { requestError.value = '确认导入失败' }
  finally { confirming.value = false }
}

async function downloadErrors(): Promise<void> {
  if (!result.value || downloading.value) return
  downloading.value = true
  downloadError.value = false
  try { downloadedFile.value = await downloadPackageErrors(result.value.id) }
  catch { downloadError.value = true }
  finally { downloading.value = false }
}

function formatBytes(value: number): string { return `${(value / 1024 / 1024).toFixed(2)} MiB` }

function formatAffected(sample: Record<string, unknown>): string {
  const values = Array.isArray(sample.affected_software_json) ? sample.affected_software_json : []
  if (!values.length) return '来源尚未提供'
  return values.map((raw) => {
    const item = raw as Record<string, unknown>
    const name = [item.vendor, item.product].filter(Boolean).join('/')
    if (item.version && item.version !== '*') return `${name} ${item.version}`
    const start = item.version_start_including ?? item.version_start_excluding
    const end = item.version_end_including ?? item.version_end_excluding
    return `${name} ${start ?? '*'} → ${end ?? '*'}`
  }).join('；')
}

function formatScore(sample: Record<string, unknown>): string {
  if (sample.cvss31_score === null || sample.cvss31_score === undefined) return '来源未提供'
  return `${sample.cvss31_score} ${sample.cvss31_severity ?? ''}`.trim()
}
</script>

<style scoped>
.package-page{max-width:1380px;margin:0 auto;padding:48px 32px 80px}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:32px}.eyebrow{margin:0;color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.18em}.page-heading h1{margin:9px 0 10px;color:var(--ink);font:750 clamp(42px,6vw,68px)/.95 var(--font-display);letter-spacing:-.045em}.page-heading>div>span{color:var(--text-muted);line-height:1.7}.contract-seal{width:124px;padding:18px;border:1px solid var(--line-strong);border-top:5px solid var(--brand-red);background:#fff}.contract-seal small,.contract-seal span{display:block;color:var(--text-muted);font-size:9px;font-weight:900;letter-spacing:.14em}.contract-seal strong{display:block;margin:5px 0;color:var(--ink);font:800 34px var(--font-display)}.step-rail{display:grid;grid-template-columns:repeat(4,1fr);margin:36px 0 16px;padding:0;list-style:none}.step-rail li{display:flex;align-items:center;gap:12px;min-height:72px;padding:14px 18px;border:1px solid var(--line-strong);background:#fff}.step-rail li.active{color:#fff;background:var(--ink)}.step-rail li[aria-disabled=true]{color:#8b949c;background:var(--paper-warm)}.step-rail>li>span{font:800 23px var(--font-display)}.step-rail strong,.step-rail small{display:block}.step-rail small{margin-top:4px;font-size:10px;opacity:.66}.upload-gate{display:grid;grid-template-columns:1fr 1.1fr;border:1px solid var(--line-strong);background:#fff}.gate-copy{padding:35px;color:#fff;background:var(--ink)}.gate-copy h2{margin:13px 0 10px;font:750 29px var(--font-display)}.gate-copy p{color:rgba(255,255,255,.65);line-height:1.75}.gate-copy ul{display:flex;gap:8px;margin:24px 0 0;padding:0;list-style:none}.gate-copy li{padding:7px 10px;border:1px solid rgba(255,255,255,.2);font-size:10px;font-weight:800}.file-control{display:flex;flex-direction:column;justify-content:center;padding:35px}.file-control>label{margin-bottom:9px;font-weight:800}.file-picker{position:relative;display:flex;align-items:center;gap:16px;min-height:88px;padding:18px;border:1px dashed var(--line-strong);background:var(--paper-warm)}.file-picker.selected{border-style:solid;background:#fff}.file-picker input{position:absolute;inset:0;width:100%;height:100%;opacity:0}.file-icon{display:grid;place-items:center;width:54px;height:54px;color:#fff;background:var(--brand-red);font-weight:900}.file-picker strong,.file-picker small{display:block}.file-picker small{margin-top:7px;color:var(--text-muted)}.primary,.write-action button,.section-heading button{min-height:44px;margin-top:14px;padding:10px 16px;border:1px solid var(--brand-red);color:#fff;background:var(--brand-red);font-weight:800}.feedback,.validating{margin:16px 0 0;padding:14px 17px;border-left:4px solid}.feedback.error{display:flex;flex-direction:column;border-color:var(--brand-red);background:#fff1f2}.feedback.success{border-color:var(--success);background:#edf9f4}.validating{display:flex;gap:12px;border:1px solid var(--line-strong);background:#fff}.validating i{width:12px;height:12px;border-radius:50%;background:var(--brand-red)}.validating strong{display:block}.result-banner{display:flex;align-items:center;justify-content:space-between;margin-top:22px;padding:27px 30px;border:1px solid var(--line-strong);border-left:7px solid var(--success);background:#fff}.result-banner.failed{border-left-color:var(--brand-red)}.result-banner h2{margin:8px 0 6px;font:750 29px var(--font-display)}.result-banner p{margin:0;color:var(--text-muted)}.status-mark{font:800 30px var(--font-display)}.source-strip{display:grid;grid-template-columns:1.2fr 1.4fr 1fr;gap:1px;margin-top:10px;border:1px solid var(--line-strong);background:var(--line)}.source-strip>div{padding:16px;background:#fff}.source-strip small,.source-strip strong{display:block}.source-strip small{color:var(--text-muted);font-size:9px}.source-strip strong{margin-top:7px;font-size:11px}.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:10px 0}.metrics article{padding:20px;border:1px solid var(--line-strong);border-top:4px solid #75808a;background:#fff}.metrics article.new{border-top-color:var(--success)}.metrics article.conflict,.metrics article.error{border-top-color:var(--brand-red)}.metrics small{display:block;color:var(--text-muted)}.metrics strong{display:block;margin-top:12px;font:750 30px var(--font-display)}.sample-ledger,.file-ledger,.write-action,.error-ledger{border:1px solid var(--line-strong);background:#fff}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--line)}.section-heading h2{margin:5px 0 0;font:750 23px var(--font-display)}.section-heading p{margin:0;color:var(--text-muted);font-size:11px}.section-heading button{margin:0}.sample-card{padding:20px 24px;border-bottom:1px solid var(--line)}.sample-card>div{display:flex;align-items:center;gap:12px}.sample-card span{padding:4px 8px;background:var(--paper-warm);font-size:10px}.sample-card p{color:var(--text-muted)}.sample-card dl{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin:0}.sample-card dt{color:var(--text-muted);font-size:9px}.sample-card dd{margin:5px 0 0;font-size:12px}.evidence-grid{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:12px;margin-top:12px}.write-action{padding:27px;color:#fff;background:var(--ink)}.write-action h2{font:750 23px var(--font-display)}.write-action p{color:rgba(255,255,255,.65);line-height:1.7}.succeeded-panel{border-top:5px solid var(--success)}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:13px 15px;border-bottom:1px solid var(--line);text-align:left}th{background:var(--paper-warm);font-size:9px}td{font-size:12px}.mono{font-family:Consolas,"Cascadia Mono",monospace}.code{color:var(--brand-red-deep)}.rejected{max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.error-ledger{margin-top:12px}.truncated{padding:12px 24px;color:var(--brand-red-deep)}@media(max-width:900px){.upload-gate,.evidence-grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(3,1fr)}.source-strip{grid-template-columns:1fr}.step-rail{grid-template-columns:1fr 1fr}}@media(max-width:600px){.package-page{padding:28px 14px}.page-heading{align-items:flex-start;flex-direction:column}.metrics{grid-template-columns:repeat(2,1fr)}.step-rail{grid-template-columns:1fr}.sample-card dl{grid-template-columns:1fr}}
</style>
