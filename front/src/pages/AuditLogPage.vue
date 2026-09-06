<template>
  <main class="audit-page">
    <header><p>SYSTEM MANAGEMENT / AUDIT</p><h1>变更记录</h1><span>只读追溯已成功提交的数据库业务变更。</span></header>
    <form class="filters" @submit.prevent="applyFilters">
      <label>对象<select v-model="draft.objectType"><option value="">全部对象</option><option v-for="item in objectTypes" :key="item" :value="item">{{ objectNames[item] ?? item }}</option></select></label>
      <label>操作者 ID<input v-model.number="draft.userId" type="number" min="1" placeholder="全部用户"></label>
      <label>动作<select v-model="draft.action"><option value="">全部动作</option><option v-for="item in actions" :key="item" :value="item">{{ actionNames[item] }}</option></select></label>
      <label>开始时间<input v-model="draft.createdFrom" type="datetime-local"></label>
      <label>结束时间<input v-model="draft.createdTo" type="datetime-local"></label>
      <button :disabled="loading">{{ loading ? '查询中…' : '查询' }}</button>
    </form>
    <p v-if="error" class="notice error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
    <p v-else-if="loading" class="notice" aria-live="polite">正在读取变更记录…</p>
    <section v-else class="records">
      <p class="summary">共 {{ page?.total ?? 0 }} 条记录</p>
      <p v-if="!page?.items.length" data-state="empty" class="notice">没有符合条件的变更记录。</p>
      <table v-else><thead><tr><th>时间</th><th>对象</th><th>操作者</th><th>动作</th><th>关键字段</th><th></th></tr></thead><tbody>
        <tr v-for="item in page.items" :key="item.id"><td>{{ formatTime(item.created_at) }}</td><td>{{ objectNames[item.object_type] ?? item.object_type }} #{{ item.object_id ?? '批量' }}</td><td>{{ item.actor_display_name ?? '系统任务' }}</td><td>{{ actionNames[item.action] }}</td><td>{{ item.detail_keys.join('、') || '—' }}</td><td><button type="button" :aria-label="`查看变更记录 ${item.id}`" @click="openDetail(item.id)">查看差异</button></td></tr>
      </tbody></table>
      <nav class="pager" aria-label="变更记录分页"><button type="button" :disabled="cursorHistory.length === 0" @click="previousPage">上一页</button><button type="button" :disabled="!page?.next_cursor" @click="nextPage">下一页</button></nav>
    </section>
    <div v-if="detail" class="overlay" @click.self="detail = null"><section role="dialog" aria-modal="true" aria-labelledby="audit-detail-title"><button class="close" aria-label="关闭差异" @click="detail = null">×</button><p>READ ONLY</p><h2 id="audit-detail-title">变更记录 #{{ detail.id }}</h2><dl><dt>时间</dt><dd>{{ formatTime(detail.created_at) }}</dd><dt>操作者</dt><dd>{{ detail.actor_display_name ?? '系统任务' }}</dd><dt>对象</dt><dd>{{ objectNames[detail.object_type] ?? detail.object_type }} #{{ detail.object_id ?? '批量' }}</dd><dt>动作</dt><dd>{{ actionNames[detail.action] }}</dd></dl><h3>关键字段差异</h3><pre data-field="audit-detail">{{ formatDetail(detail.detail) }}</pre></section></div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AuditOperationsApiError, getAuditLog, listAuditLogs, type AuditLogDetail, type AuditLogPage as AuditPage } from '../api/auditOperations'

const objectTypes = ['app_user','user_product_scope','product','product_version','ots_component','product_ots','import_batch','vulnerability','vulnerability_ots_match','product_assessment']
const objectNames: Record<string,string> = { app_user:'用户',user_product_scope:'产品授权',product:'产品',product_version:'产品版本',ots_component:'OTS',product_ots:'产品 OTS',import_batch:'导入批次',vulnerability:'漏洞事实',vulnerability_ots_match:'候选匹配',product_assessment:'产品评估' }
const actions = ['insert','update','delete','batch_upsert'] as const
const actionNames: Record<string,string> = { insert:'新增',update:'更新',delete:'删除',batch_upsert:'批量写入' }
const draft = reactive({ objectType:'', userId: undefined as number|undefined, action:'', createdFrom:'', createdTo:'' })
const active = reactive({ ...draft }), page = ref<AuditPage|null>(null), detail = ref<AuditLogDetail|null>(null)
const loading = ref(true), error = ref(''), currentCursor = ref<string|undefined>(), cursorHistory = ref<string[]>([])

onMounted(load)
async function load(): Promise<void> { loading.value=true; error.value=''; try { page.value=await listAuditLogs({ ...active, cursor:currentCursor.value }) } catch (cause) { error.value=cause instanceof AuditOperationsApiError && cause.status===403?'无权访问变更记录':'变更记录暂时不可用，请稍后重试。' } finally { loading.value=false } }
async function applyFilters(): Promise<void> { Object.assign(active,draft); currentCursor.value=undefined; cursorHistory.value=[]; await load() }
async function nextPage(): Promise<void> { if(!page.value?.next_cursor)return; cursorHistory.value.push(currentCursor.value??''); currentCursor.value=page.value.next_cursor; await load() }
async function previousPage(): Promise<void> { const prior=cursorHistory.value.pop(); currentCursor.value=prior||undefined; await load() }
async function openDetail(id:number): Promise<void> { error.value=''; try { detail.value=await getAuditLog(id) } catch { error.value='变更详情暂时不可用，请重试。' } }
function formatTime(value:string):string { return new Date(value).toLocaleString('zh-CN') }
function formatDetail(value:unknown):string { return value == null?'无详情':JSON.stringify(value,null,2) }
</script>

<style scoped>
.audit-page{max-width:1220px;margin:0 auto;padding:48px 32px}header p,.overlay p{color:var(--brand-red);font-size:10px;font-weight:900;letter-spacing:.16em}h1{margin:8px 0;color:var(--ink);font:750 58px/1 var(--font-display)}header span{color:var(--text-muted)}.filters{display:grid;grid-template-columns:1.2fr .8fr 1fr 1.2fr 1.2fr auto;gap:10px;align-items:end;margin-top:28px;padding:20px;border:1px solid var(--line-strong);background:#fff}.filters label{display:grid;gap:7px;font-size:11px;font-weight:800}.filters input,.filters select{min-height:40px;border:1px solid var(--line-strong);padding:0 9px;background:#fff}.filters button,.records button,.notice button{min-height:40px;border:1px solid var(--line-strong);padding:0 14px;background:#fff;font-weight:800;cursor:pointer}.filters>button{border-color:var(--brand-red);color:#fff;background:var(--brand-red)}.notice{margin-top:24px;padding:16px;border-left:4px solid var(--line-strong);background:#fff}.notice.error{border-color:var(--brand-red);color:var(--danger)}.records{margin-top:20px}.summary{color:var(--text-muted);font-size:12px}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:13px;border-bottom:1px solid var(--line);text-align:left;font-size:12px}th{color:var(--text-muted);background:var(--paper-warm)}.pager{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}.pager button:disabled{opacity:.4}.overlay{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:20px;background:rgba(20,24,28,.6)}.overlay section{position:relative;width:min(720px,100%);max-height:85vh;overflow:auto;padding:28px;background:#fff}.close{position:absolute;right:16px;top:12px;border:0;background:transparent;font-size:28px}.overlay dl{display:grid;grid-template-columns:90px 1fr;gap:8px}.overlay dt{color:var(--text-muted)}.overlay dd{margin:0}.overlay pre{overflow:auto;padding:16px;background:#202428;color:#f7f8fa;white-space:pre-wrap;word-break:break-word}@media(max-width:960px){.filters{grid-template-columns:1fr 1fr}table{display:block;overflow:auto}}@media(max-width:620px){.audit-page{padding:28px 14px}.filters{grid-template-columns:1fr}h1{font-size:42px}}
</style>
