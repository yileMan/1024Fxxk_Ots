<template>
  <main class="package-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">DATA EXCHANGE / PACKAGE GATE</p>
        <h1>数据包导入</h1>
        <span>在任何业务写入之前，检查离线 ZIP 的结构、摘要、范围与引用闭包。</span>
      </div>
      <div class="contract-seal" aria-label="当前数据包格式版本">
        <small>CONTRACT</small><strong>1.0</strong><span>ZIP / CSV</span>
      </div>
    </header>

    <ol class="step-rail" aria-label="数据包导入步骤">
      <li data-step="upload" :class="{ active: !result }"><span>01</span><div><strong>上传数据包</strong><small>选择单个规范 ZIP</small></div></li>
      <li data-step="validate" :class="{ active: !!result }"><span>02</span><div><strong>校验预览</strong><small>只读分类与错误证据</small></div></li>
      <li data-step="confirm" aria-disabled="true"><span>03</span><div><strong>确认导入</strong><small>后续能力尚未开放</small></div></li>
      <li data-step="result" aria-disabled="true"><span>04</span><div><strong>查看结果</strong><small>后续能力尚未开放</small></div></li>
    </ol>

    <section class="upload-gate">
      <div class="gate-copy">
        <small>CONTROLLED INTAKE</small>
        <h2>离线包校验闸门</h2>
        <p>文件保留在内网受控目录；校验过程不会访问互联网，也不会创建漏洞、候选关系或评估任务。</p>
        <ul>
          <li>固定十文件根目录</li><li>SHA-256 摘要闭包</li><li>范围内 OTS 引用</li>
        </ul>
      </div>
      <div class="file-control">
        <label for="package-file">选择数据包</label>
        <div class="file-picker" :class="{ selected: selectedFile }">
          <input id="package-file" type="file" accept=".zip,application/zip" :disabled="submitting" @change="selectFile">
          <span class="file-icon" aria-hidden="true">ZIP</span>
          <div>
            <strong>{{ selectedFile?.name ?? '拖入或选择规范 ZIP' }}</strong>
            <small>{{ selectedFile ? formatBytes(selectedFile.size) : '文件名 ots_intelligence_YYYYMMDD_HHMMSS.zip · 最大 50 MiB' }}</small>
          </div>
        </div>
        <button class="primary" data-action="validate" :disabled="!selectedFile || !!selectionError || submitting" @click="validateSelected">
          {{ submitting ? '正在上传并校验…' : '上传并开始校验' }}
        </button>
      </div>
    </section>

    <p v-if="selectionError" class="feedback error" role="alert">{{ selectionError }}</p>
    <p v-if="requestError" class="feedback error" role="alert"><strong>上传或校验失败</strong><span>本次未展示旧结果，请检查服务后重试。</span></p>
    <p v-if="downloadError" class="feedback error" role="alert">错误清单下载失败，请稍后重试。</p>
    <p v-if="downloadedFile" class="feedback success" aria-live="polite">已下载 {{ downloadedFile }}</p>
    <p v-if="submitting" class="validating" aria-live="polite"><i></i><span><strong>正在执行受限校验</strong>上传完成后依次检查 ZIP、manifest、CSV、摘要、范围和引用。</span></p>

    <template v-if="result">
      <section class="result-banner" :class="result.status">
        <div>
          <small>{{ result.status === 'validated' ? 'VALIDATED / READ ONLY' : 'FAILED / ACTION REQUIRED' }}</small>
          <h2>{{ result.status === 'validated' ? '校验通过，尚未正式写入' : '校验未通过' }}</h2>
          <p>批次 {{ result.batch_no }} · 范围 {{ result.scope_count }} 个 OTS · 格式 {{ result.format_version }}</p>
        </div>
        <span class="status-mark" aria-hidden="true">{{ result.status === 'validated' ? '✓' : '!' }}</span>
      </section>

      <section class="metrics" aria-label="分类统计">
        <article><small>全部记录</small><strong>{{ result.summary.total }}</strong></article>
        <article class="new"><small>新增</small><strong>{{ result.summary.new }}</strong></article>
        <article><small>更新</small><strong>{{ result.summary.update }}</strong></article>
        <article><small>重复</small><strong>{{ result.summary.duplicate }}</strong></article>
        <article class="conflict"><small>冲突</small><strong>{{ result.summary.conflict }}</strong></article>
        <article class="error"><small>错误</small><strong>{{ result.summary.error }}</strong></article>
      </section>

      <section class="evidence-grid">
        <article class="file-ledger">
          <div class="section-heading"><div><small>FILE LEDGER</small><h2>文件级证据</h2></div><p>分类依据：包内结构 v1</p></div>
          <div v-if="fileEntries.length === 0" class="empty-inline">领域文件没有可预览记录。</div>
          <div v-else class="table-scroll">
            <table>
              <thead><tr><th>文件</th><th>总计</th><th>新增</th><th>重复</th><th>冲突</th><th>错误</th><th>样例</th></tr></thead>
              <tbody>
                <tr v-for="[name, stats] in fileEntries" :key="name">
                  <td class="mono"><strong>{{ name }}</strong></td><td>{{ stats.total }}</td><td>{{ stats.new }}</td><td>{{ stats.duplicate }}</td><td>{{ stats.conflict }}</td><td>{{ stats.error }}</td>
                  <td class="sample">{{ sampleLabel(stats.samples[0]) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <aside class="write-lock">
          <span aria-hidden="true">LOCKED</span>
          <small>WRITE BOUNDARY</small>
          <h2>正式写入保持关闭</h2>
          <p>本阶段只保存批次校验证据。确认导入、覆盖推进和评估任务将在后续 change 开放。</p>
          <button type="button" disabled>确认导入尚未开放</button>
        </aside>
      </section>

      <section v-if="result.status === 'failed'" class="error-ledger">
        <div class="section-heading">
          <div><small>REJECTION LEDGER</small><h2>错误清单</h2></div>
          <button data-action="download-errors" :disabled="downloading" @click="downloadErrors">{{ downloading ? '正在下载…' : '下载错误清单 CSV' }}</button>
        </div>
        <p v-if="result.truncated_error_count > 0" class="truncated">另有 {{ result.truncated_error_count }} 项未在页面展示，请下载有界错误清单。</p>
        <div class="table-scroll">
          <table>
            <thead><tr><th>文件</th><th>位置</th><th>字段</th><th>错误码</th><th>原因</th><th>拒绝值</th></tr></thead>
            <tbody><tr v-for="(error, index) in result.errors" :key="`${error.file_name}-${error.row_number}-${index}`">
              <td class="mono">{{ error.file_name }}</td><td>{{ error.row_number ? `第 ${error.row_number} 行` : '文件级' }}</td><td class="mono">{{ error.field ?? '—' }}</td><td class="mono code">{{ error.error_code }}</td><td>{{ error.reason }}</td><td class="rejected">{{ error.rejected_value ?? '—' }}</td>
            </tr></tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  downloadPackageErrors,
  getImportPackage,
  validateImportPackage,
  type ImportPackageResult,
} from '../api/importPackages'

const MAX_FILE_BYTES = 50 * 1024 * 1024
const PACKAGE_NAME = /^ots_intelligence_\d{8}_\d{6}\.zip$/
const selectedFile = ref<File | null>(null)
const selectionError = ref('')
const requestError = ref(false)
const downloadError = ref(false)
const downloadedFile = ref('')
const submitting = ref(false)
const downloading = ref(false)
const result = ref<ImportPackageResult | null>(null)
const fileEntries = computed(() => Object.entries(result.value?.file_stats ?? {}).filter(([, stats]) => stats.total > 0 || stats.error > 0))

onMounted(async () => {
  const batchId = Number(new URL(window.location.href).searchParams.get('batch'))
  if (!Number.isInteger(batchId) || batchId <= 0) return
  submitting.value = true
  try {
    result.value = await getImportPackage(batchId)
  } catch {
    requestError.value = true
  } finally {
    submitting.value = false
  }
})

function selectFile(event: Event): void {
  result.value = null
  requestError.value = false
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
  requestError.value = false
  downloadError.value = false
  downloadedFile.value = ''
  submitting.value = true
  try {
    result.value = await validateImportPackage(file)
    const url = new URL(window.location.href)
    url.searchParams.set('batch', String(result.value.id))
    window.history.replaceState({}, '', url)
  } catch {
    requestError.value = true
  } finally {
    submitting.value = false
  }
}

async function downloadErrors(): Promise<void> {
  if (!result.value || downloading.value) return
  downloading.value = true
  downloadError.value = false
  downloadedFile.value = ''
  try {
    downloadedFile.value = await downloadPackageErrors(result.value.id)
  } catch {
    downloadError.value = true
  } finally {
    downloading.value = false
  }
}

function formatBytes(value: number): string {
  return `${(value / 1024 / 1024).toFixed(2)} MiB`
}

function sampleLabel(sample: Record<string, string> | undefined): string {
  if (!sample) return '—'
  return sample.cve_id ?? sample.ots_id ?? Object.values(sample)[0] ?? '—'
}
</script>

<style scoped>
.package-page{max-width:1380px;margin:0 auto;padding:48px 32px 80px}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:32px}.eyebrow{margin:0;color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.18em}.page-heading h1{margin:9px 0 10px;color:var(--ink);font:750 clamp(42px,6vw,68px)/.95 var(--font-display);letter-spacing:-.045em}.page-heading>div>span{color:var(--text-muted);line-height:1.7}.contract-seal{width:124px;height:124px;display:flex;flex-direction:column;justify-content:center;padding:18px;border:1px solid var(--line-strong);border-top:5px solid var(--brand-red);background:#fff;box-shadow:var(--shadow-card)}.contract-seal small,.contract-seal span{color:var(--text-muted);font-size:9px;font-weight:900;letter-spacing:.16em}.contract-seal strong{margin:5px 0;color:var(--ink);font:800 34px var(--font-display)}.step-rail{display:grid;grid-template-columns:repeat(4,1fr);margin:36px 0 16px;padding:0;list-style:none}.step-rail li{position:relative;display:flex;align-items:center;gap:12px;min-height:82px;padding:15px 18px;border:1px solid var(--line-strong);border-right:0;background:#fff}.step-rail li:last-child{border-right:1px solid var(--line-strong)}.step-rail li:after{position:absolute;right:-7px;z-index:2;width:12px;height:12px;border-top:1px solid var(--line-strong);border-right:1px solid var(--line-strong);background:inherit;content:"";transform:rotate(45deg)}.step-rail li:last-child:after{display:none}.step-rail li.active{z-index:1;color:#fff;background:var(--ink)}.step-rail li[aria-disabled=true]{color:#8b949c;background:var(--paper-warm)}.step-rail>li>span{font:800 23px var(--font-display)}.step-rail strong,.step-rail small{display:block}.step-rail strong{font-size:13px}.step-rail small{margin-top:5px;color:inherit;font-size:10px;opacity:.65}.upload-gate{display:grid;grid-template-columns:1fr 1.1fr;min-height:280px;border:1px solid var(--line-strong);background:#fff;box-shadow:var(--shadow-card)}.gate-copy{position:relative;overflow:hidden;padding:35px;color:#fff;background:var(--ink)}.gate-copy:after{position:absolute;right:-70px;bottom:-105px;width:250px;height:250px;border:25px solid var(--brand-red);border-radius:50%;content:"";opacity:.82}.gate-copy>*{position:relative;z-index:1}.gate-copy small,.section-heading small{font-size:10px;font-weight:900;letter-spacing:.17em}.gate-copy h2{margin:13px 0 10px;font:750 29px var(--font-display)}.gate-copy p{max-width:580px;color:rgba(255,255,255,.62);line-height:1.75}.gate-copy ul{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0 0;padding:0;list-style:none}.gate-copy li{padding:7px 10px;border:1px solid rgba(255,255,255,.19);font-size:10px;font-weight:800}.file-control{display:flex;flex-direction:column;justify-content:center;padding:35px}.file-control>label{margin-bottom:9px;color:var(--ink);font-size:12px;font-weight:800}.file-picker{position:relative;display:flex;align-items:center;gap:16px;min-height:96px;padding:18px;border:1px dashed var(--line-strong);background:var(--paper-warm)}.file-picker.selected{border-style:solid;border-color:#777f86;background:#fff}.file-picker input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer}.file-icon{display:grid;place-items:center;width:54px;height:54px;flex:0 0 auto;color:#fff;background:var(--brand-red);font:900 11px var(--font-display);letter-spacing:.1em}.file-picker strong,.file-picker small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-picker strong{max-width:520px;color:var(--ink);font-size:13px}.file-picker small{max-width:520px;margin-top:7px;color:var(--text-muted);font-size:10px}.primary,.section-heading button{min-height:44px;margin-top:14px;border:1px solid var(--brand-red);padding:10px 16px;color:#fff;background:var(--brand-red);font-weight:800;cursor:pointer}.primary:disabled,.section-heading button:disabled{opacity:.5;cursor:wait}.feedback{display:flex;gap:8px;margin:16px 0 0;padding:14px 17px;border-left:4px solid}.feedback.error{flex-direction:column;border-color:var(--brand-red);background:#fff1f2;color:var(--brand-red-deep)}.feedback.success{border-color:var(--success);background:#edf9f4;color:#126348}.validating{display:flex;align-items:center;gap:14px;margin:16px 0 0;padding:18px;border:1px solid var(--line-strong);background:#fff}.validating i{width:12px;height:12px;border-radius:50%;background:var(--brand-red);animation:pulse 1s ease-in-out infinite}.validating strong{display:block;margin-bottom:3px;color:var(--ink)}.result-banner{display:flex;align-items:center;justify-content:space-between;margin-top:22px;padding:27px 30px;border:1px solid var(--line-strong);border-left:7px solid var(--success);background:#fff}.result-banner.failed{border-left-color:var(--brand-red)}.result-banner small{color:var(--success);font-size:10px;font-weight:900;letter-spacing:.15em}.result-banner.failed small{color:var(--brand-red)}.result-banner h2{margin:8px 0 6px;color:var(--ink);font:750 29px var(--font-display)}.result-banner p{margin:0;color:var(--text-muted);font-size:12px}.status-mark{display:grid;place-items:center;width:62px;height:62px;border:2px solid var(--success);border-radius:50%;color:var(--success);font:800 30px var(--font-display)}.failed .status-mark{border-color:var(--brand-red);color:var(--brand-red)}.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:10px 0}.metrics article{padding:20px;border:1px solid var(--line-strong);border-top:4px solid #75808a;background:#fff}.metrics article.new{border-top-color:var(--success)}.metrics article.conflict,.metrics article.error{border-top-color:var(--brand-red)}.metrics small{display:block;color:var(--text-muted);font-size:10px;font-weight:900;letter-spacing:.08em}.metrics strong{display:block;margin-top:14px;color:var(--ink);font:750 30px var(--font-display)}.evidence-grid{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:12px}.file-ledger,.write-lock,.error-ledger{border:1px solid var(--line-strong);background:#fff}.section-heading{display:flex;align-items:flex-end;justify-content:space-between;padding:22px 24px;border-bottom:1px solid var(--line)}.section-heading small{color:var(--text-muted)}.section-heading h2{margin:5px 0 0;color:var(--ink);font:750 23px var(--font-display)}.section-heading p{margin:0;color:var(--text-muted);font-size:11px}.section-heading button{margin:0}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:14px 16px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--text-muted);background:var(--paper-warm);font-size:9px;letter-spacing:.1em}td{font-size:12px}.mono{font-family:Consolas,"Cascadia Mono",monospace}.sample,.rejected{max-width:220px;overflow:hidden;color:var(--text-muted);text-overflow:ellipsis;white-space:nowrap}.code{color:var(--brand-red-deep);font-size:10px}.write-lock{position:relative;overflow:hidden;padding:27px;color:#fff;background:var(--ink)}.write-lock>span{display:block;margin-bottom:28px;color:rgba(255,255,255,.08);font:900 44px var(--font-display);letter-spacing:-.05em}.write-lock small{color:#ff777c;font-size:9px;font-weight:900;letter-spacing:.16em}.write-lock h2{margin:10px 0;color:#fff;font:750 23px var(--font-display)}.write-lock p{color:rgba(255,255,255,.58);font-size:12px;line-height:1.7}.write-lock button{width:100%;margin-top:17px;padding:12px;border:1px solid rgba(255,255,255,.15);color:rgba(255,255,255,.44);background:transparent}.error-ledger{margin-top:12px}.truncated{margin:0;padding:12px 24px;border-bottom:1px solid #f2d2d4;color:var(--brand-red-deep);background:#fff8f8;font-size:11px}.empty-inline{padding:30px;color:var(--text-muted)}@keyframes pulse{50%{transform:scale(.55);opacity:.35}}@media(max-width:1080px){.metrics{grid-template-columns:repeat(3,1fr)}.evidence-grid{grid-template-columns:1fr}.write-lock{min-height:230px}}@media(max-width:760px){.package-page{padding:28px 14px 50px}.page-heading{align-items:flex-start;flex-direction:column}.contract-seal{width:100%;height:auto}.step-rail{grid-template-columns:1fr}.step-rail li{border-right:1px solid var(--line-strong);border-bottom:0}.step-rail li:last-child{border-bottom:1px solid var(--line-strong)}.step-rail li:after{display:none}.upload-gate{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.file-control,.gate-copy{padding:25px}.result-banner{align-items:flex-start}.status-mark{width:48px;height:48px}.section-heading{align-items:flex-start;flex-direction:column;gap:12px}}@media(prefers-reduced-motion:reduce){.validating i{animation:none}}
</style>
