<template>
  <section class="ots-manager">
    <header><div><strong>产品 OTS 清单</strong><small>关联共享 OTS 主数据，不复制组件信息</small></div><div class="tools"><button type="button" @click="downloadProductOtsTemplate">下载 CSV 模板</button><button type="button" :disabled="busy" @click="exportProductOts(versionId)">导出当前清单</button></div></header>
    <div class="associate"><label>选择 OTS<select v-model.number="selectedOtsId"><option :value="0">请选择已有 OTS</option><option v-for="item in available" :key="item.id" :value="item.id">{{ item.ots_name }} · {{ item.ots_version }}</option></select></label><button type="button" :disabled="!selectedOtsId||busy" @click="addSelected">添加关联</button></div>
    <p v-if="loading">正在读取 OTS 清单…</p><p v-else-if="loadError" role="alert">OTS 清单暂时不可用，请稍后重试</p><p v-else-if="items.length===0" class="empty">当前版本尚未关联 OTS</p>
    <table v-else><thead><tr><th>OTS</th><th>官方网站</th><th>EOL</th><th>操作</th></tr></thead><tbody><tr v-for="item in items" :key="item.id"><td><strong>{{ item.ots_name }}</strong><small>{{ item.ots_version }}</small></td><td><a :href="item.official_website" target="_blank" rel="noreferrer">{{ item.official_website }}</a></td><td>{{ item.is_eol?'是':'否' }}</td><td><button type="button" :aria-label="`移除${item.ots_name}`" @click="remove(item)">移除</button></td></tr></tbody></table>
    <div class="import-zone"><label>批量导入 CSV<input type="file" accept=".csv,text/csv" @change="selectFile"></label><button type="button" data-action="import-product-ots" :disabled="!file||busy" @click="runImport">{{ busy?'正在导入…':'导入清单' }}</button></div>
    <p v-if="feedback" class="feedback">{{ feedback }}</p><ul v-if="errors.length" class="csv-errors" role="alert"><li v-for="error in errors" :key="`${error.row}-${error.field}`">第 {{ error.row }} 行 · {{ error.field }} · {{ error.reason }}</li></ul>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { createProductOts, downloadProductOtsTemplate, exportProductOts, importProductOts, listOts, listProductOts, OtsApiError, removeProductOts, type CsvImportError, type Ots, type ProductOts } from '../api/ots'
const props=defineProps<{versionId:number}>()
const items=ref<ProductOts[]>([]);const catalog=ref<Ots[]>([]);const selectedOtsId=ref(0);const loading=ref(true);const loadError=ref(false);const busy=ref(false);const file=ref<File|null>(null);const errors=ref<CsvImportError[]>([]);const feedback=ref('')
const available=computed(()=>catalog.value.filter(item=>!items.value.some(link=>link.ots_component_id===item.id)))
onMounted(load)
async function load(){loading.value=true;loadError.value=false;try{const[page,links]=await Promise.all([listOts({pageSize:100}),listProductOts(props.versionId)]);catalog.value=page.items;items.value=links}catch{loadError.value=true}finally{loading.value=false}}
async function addSelected(){if(!selectedOtsId.value)return;busy.value=true;feedback.value='';try{await createProductOts(props.versionId,selectedOtsId.value);selectedOtsId.value=0;await load()}catch(e){feedback.value=e instanceof OtsApiError&&e.code==='PRODUCT_OTS_CONFLICT'?'该 OTS 已在当前清单中':'添加关联失败，请稍后重试'}finally{busy.value=false}}
async function remove(item:ProductOts){if(!confirm(`从当前产品版本移除 ${item.ots_name}？OTS 主数据不会删除。`))return;try{await removeProductOts(props.versionId,item.id);await load()}catch(e){feedback.value=e instanceof OtsApiError&&e.code==='PRODUCT_OTS_HISTORY_CONFLICT'?'该关联已有历史评估，不能移除':'移除失败，请稍后重试'}}
function selectFile(event:Event){file.value=(event.target as HTMLInputElement).files?.[0]??null;errors.value=[];feedback.value=''}
async function runImport(){if(!file.value)return;busy.value=true;errors.value=[];feedback.value='';try{const result=await importProductOts(props.versionId,file.value);feedback.value=`导入完成：新增 OTS ${result.created_ots}，新增关联 ${result.created_relations}，已存在 ${result.existing_relations}`;await load()}catch(e){if(e instanceof OtsApiError&&e.errors.length)errors.value=e.errors;else feedback.value='导入失败，请检查文件后重试'}finally{busy.value=false}}
</script>

<style scoped>
.ots-manager{display:grid;gap:16px}.ots-manager>header,.tools,.associate,.import-zone{display:flex;align-items:end;justify-content:space-between;gap:10px}.ots-manager small{display:block;color:var(--text-muted);margin-top:4px}.tools{justify-content:flex-end}.associate label,.import-zone label{display:grid;gap:6px;flex:1}.associate select{width:100%}.empty,.feedback{padding:14px;background:var(--paper-warm);border-left:3px solid var(--brand-red)}table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid var(--line);text-align:left}a{color:var(--brand-red-deep);word-break:break-all}.csv-errors{margin:0;padding:12px 12px 12px 32px;background:#fff1f2;color:var(--brand-red-deep)}button,select,input{font:inherit;min-height:40px;padding:7px 10px;border:1px solid var(--line-strong);background:#fff}@media(max-width:700px){.ots-manager>header,.associate,.import-zone{align-items:stretch;flex-direction:column}.tools{justify-content:stretch;flex-wrap:wrap}}
</style>
