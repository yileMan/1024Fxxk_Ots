<template>
  <main class="my-products-page">
    <header>
      <p>AUTHORIZED PRODUCTS / READ ONLY</p>
      <h1>我的产品</h1>
      <span>仅展示当前授权范围内的产品、版本和 OTS 清单；所有主数据修改仍由管理员完成。</span>
    </header>

    <p v-if="loading" class="state">正在读取授权产品…</p>
    <p v-else-if="accessForbidden" class="state error" role="alert">产品授权已失效或无权访问，请联系管理员确认授权范围</p>
    <p v-else-if="loadError" class="state error" role="alert">我的产品暂时不可用，请稍后重试</p>
    <section v-else-if="products.length === 0" class="state empty" data-state="empty">
      <strong>当前没有有效的产品授权</strong>
      <span>如需访问产品，请联系管理员配置产品级或版本级范围。</span>
    </section>

    <section v-else class="workspace">
      <table>
        <thead><tr><th>产品编号</th><th>产品名称</th><th>说明</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="product in products" :key="product.id">
            <td><code>{{ product.product_code }}</code></td>
            <td><strong>{{ product.product_name }}</strong></td>
            <td>{{ product.description || '—' }}</td>
            <td><button type="button" :aria-label="`查看${product.product_name}版本`" @click="showVersions(product)">查看版本</button></td>
          </tr>
        </tbody>
      </table>
      <footer v-if="total > pageSize">
        <button type="button" :disabled="page === 1" @click="loadProducts(page - 1)">上一页</button>
        <span>第 {{ page }} 页</span>
        <button type="button" :disabled="page * pageSize >= total" @click="loadProducts(page + 1)">下一页</button>
      </footer>
    </section>

    <section v-if="selectedProduct" class="detail-panel" aria-label="授权产品版本">
      <div class="panel-heading">
        <div><small>{{ selectedProduct.product_code }}</small><h2>{{ selectedProduct.product_name }} · 授权版本</h2></div>
        <button type="button" @click="closeVersions">关闭</button>
      </div>
      <p v-if="versionsLoading" class="state compact">正在读取授权版本…</p>
      <p v-else-if="versionsError" class="state compact error" role="alert">版本列表暂时不可用，请稍后重试</p>
      <p v-else-if="versions.length === 0" class="state compact">当前授权范围内没有有效版本</p>
      <table v-else>
        <thead><tr><th>版本号</th><th>CVSS 基线</th><th>说明</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="version in versions" :key="version.id">
            <td><strong>{{ version.version_no }}</strong></td>
            <td>{{ version.primary_cvss_version }}</td>
            <td>{{ version.description || '—' }}</td>
            <td><button type="button" :aria-label="`查看版本${version.version_no} OTS清单`" @click="showOts(version)">查看 OTS</button></td>
          </tr>
        </tbody>
      </table>

      <section v-if="selectedVersion" class="ots-panel" aria-label="版本 OTS 清单">
        <div class="panel-heading"><h3>版本 {{ selectedVersion.version_no }} · OTS 清单</h3><button type="button" @click="selectedVersion = null">收起</button></div>
        <p v-if="otsLoading" class="state compact">正在读取 OTS 清单…</p>
        <p v-else-if="otsError" class="state compact error" role="alert">OTS 清单暂时不可用，请稍后重试</p>
        <p v-else-if="otsItems.length === 0" class="state compact">当前版本尚未关联 OTS</p>
        <table v-else>
          <thead><tr><th>OTS</th><th>OTS 版本</th><th>官方网站</th><th>EOL</th></tr></thead>
          <tbody><tr v-for="item in otsItems" :key="item.id"><td><strong>{{ item.ots_name }}</strong></td><td>{{ item.ots_version }}</td><td><a :href="item.official_website" target="_blank" rel="noreferrer">{{ item.official_website }}</a></td><td>{{ item.is_eol ? '已 EOL' : '未 EOL' }}</td></tr></tbody>
        </table>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listProductOts, OtsApiError, type ProductOts } from '../api/ots'
import { listProducts, listVersions, ProductApiError, type Product, type ProductVersion } from '../api/products'

const products = ref<Product[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(true)
const loadError = ref(false)
const accessForbidden = ref(false)
const selectedProduct = ref<Product | null>(null)
const versions = ref<ProductVersion[]>([])
const versionsLoading = ref(false)
const versionsError = ref(false)
const selectedVersion = ref<ProductVersion | null>(null)
const otsItems = ref<ProductOts[]>([])
const otsLoading = ref(false)
const otsError = ref(false)

async function loadProducts(targetPage = 1): Promise<void> {
  loading.value = true
  loadError.value = false
  accessForbidden.value = false
  try {
    const result = await listProducts({ page: targetPage, pageSize })
    products.value = result.items
    total.value = result.total
    page.value = result.page
  } catch (error) {
    if (error instanceof ProductApiError && error.status === 403) accessForbidden.value = true
    else loadError.value = true
  } finally {
    loading.value = false
  }
}

async function showVersions(product: Product): Promise<void> {
  selectedProduct.value = product
  selectedVersion.value = null
  versions.value = []
  versionsLoading.value = true
  versionsError.value = false
  try {
    versions.value = await listVersions(product.id)
  } catch (error) {
    if (error instanceof ProductApiError && error.status === 403) accessForbidden.value = true
    else versionsError.value = true
  } finally {
    versionsLoading.value = false
  }
}

function closeVersions(): void {
  selectedProduct.value = null
  selectedVersion.value = null
}

async function showOts(version: ProductVersion): Promise<void> {
  selectedVersion.value = version
  otsItems.value = []
  otsLoading.value = true
  otsError.value = false
  try {
    otsItems.value = await listProductOts(version.id)
  } catch (error) {
    if (error instanceof OtsApiError && error.status === 403) accessForbidden.value = true
    else otsError.value = true
  } finally {
    otsLoading.value = false
  }
}

onMounted(loadProducts)
</script>

<style scoped>
.my-products-page { max-width: 1180px; margin: 0 auto; padding: 58px 32px 80px; }
header > p { margin: 0; color: var(--amber-dark); font-size: 11px; font-weight: 900; letter-spacing: .18em; }
h1 { margin: 10px 0; color: var(--ink); font: 700 clamp(42px, 6vw, 66px)/1 var(--font-display); letter-spacing: -.04em; }
header > span { color: var(--text-muted); line-height: 1.7; }
.workspace, .detail-panel { margin-top: 28px; border: 1px solid var(--line); background: var(--paper); box-shadow: var(--shadow-card); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 15px 18px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
th { color: var(--text-muted); background: var(--paper-warm); font-size: 11px; letter-spacing: .06em; }
td { font-size: 13px; }
code { color: var(--brand-red-deep); font-weight: 800; }
button { min-height: 34px; border: 1px solid var(--line-strong); border-radius: 4px; padding: 0 13px; color: var(--ink); background: #fff; font-weight: 700; cursor: pointer; }
button:hover:not(:disabled) { border-color: var(--brand-red); color: var(--brand-red-deep); }
button:disabled { opacity: .45; cursor: not-allowed; }
footer, .panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 18px; }
.panel-heading { border-bottom: 1px solid var(--line); }
.panel-heading h2, .panel-heading h3 { margin: 3px 0 0; color: var(--ink); }
.panel-heading small { color: var(--brand-red-deep); font-weight: 800; }
.ots-panel { margin: 20px; border: 1px solid var(--line); }
.state { margin-top: 28px; padding: 28px; border: 1px solid var(--line); background: var(--paper); color: var(--text-muted); }
.state.compact { margin: 0; border: 0; }
.state.empty { display: grid; gap: 8px; }
.state.empty strong { color: var(--ink); font-size: 18px; }
.state.error { border-color: #f0bcc0; color: var(--brand-red-deep); background: #fff1f2; }
a { color: var(--brand-red-deep); }
@media (max-width: 760px) { .my-products-page { padding-inline: 18px; } .workspace, .detail-panel { overflow-x: auto; } table { min-width: 680px; } }
</style>
