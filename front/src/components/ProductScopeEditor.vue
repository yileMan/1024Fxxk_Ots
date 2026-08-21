<template>
  <section class="scope-editor" aria-labelledby="scope-title">
    <header>
      <div>
        <p>PRODUCT ACCESS</p>
        <h2 id="scope-title">{{ userDisplayName }} 的产品授权</h2>
      </div>
      <button type="button" aria-label="关闭产品授权" @click="$emit('close')">×</button>
    </header>

    <div v-if="loading" class="scope-state" aria-live="polite">正在读取产品授权…</div>
    <div v-else-if="error" class="scope-state error" role="alert">{{ error }}</div>
    <template v-else>
      <div v-if="summary?.is_global" class="global-note">管理员具有全局产品与版本读取范围，无需配置显式授权。</div>
      <form v-else data-form="scope-grant" @submit.prevent="submitGrant">
        <label>
          <span>范围类型</span>
          <select v-model="form.scopeType" name="scope_type" @change="scopeTypeChanged">
            <option value="product">产品级</option>
            <option value="version">版本级</option>
          </select>
        </label>
        <label>
          <span>产品</span>
          <select v-model="form.productId" name="product_id" required @change="productChanged">
            <option value="">选择有效产品</option>
            <option v-for="product in products" :key="product.id" :value="String(product.id)">{{ product.product_name }}（{{ product.product_code }}）</option>
          </select>
        </label>
        <label v-if="form.scopeType === 'version'">
          <span>产品版本</span>
          <select v-model="form.versionId" name="product_version_id" required>
            <option value="">选择有效版本</option>
            <option v-for="version in selectableVersions" :key="version.id" :value="String(version.id)">{{ version.version_no }}</option>
          </select>
        </label>
        <button type="submit" :disabled="submitting">{{ submitting ? '正在授权…' : '添加授权' }}</button>
      </form>

      <div v-if="summary && summary.scopes.length === 0" class="scope-state empty" data-state="empty">
        尚未配置产品范围。普通用户当前不能读取任何产品版本。
      </div>
      <ul v-else class="scope-list">
        <li v-for="scope in summary?.scopes" :key="scope.id" :class="{ ineffective: !scope.is_effective }">
          <div>
            <strong>{{ productName(scope.product_id) }}</strong>
            <span v-if="scope.scope_type === 'product'">产品级 · 覆盖该产品全部有效版本</span>
            <span v-else>版本级 · {{ versionName(scope.product_version_id) }}</span>
            <small v-if="!scope.is_effective">当前无效：产品或版本已停用</small>
          </div>
          <button type="button" :aria-label="`撤销${productName(scope.product_id)}授权`" @click="revoke(scope.id)">撤销</button>
        </li>
      </ul>
      <p v-if="actionError" class="action-error" role="alert">{{ actionError }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { listProducts, listVersions, type Product, type ProductVersion } from '../api/products'
import {
  grantUserScope,
  listUserScopes,
  revokeUserScope,
  ScopeApiError,
  type ProductScopeSummary,
} from '../api/scopes'

const props = defineProps<{ userId: number; userDisplayName: string }>()
defineEmits<{ close: [] }>()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const actionError = ref('')
const summary = ref<ProductScopeSummary | null>(null)
const products = ref<Product[]>([])
const selectableVersions = ref<ProductVersion[]>([])
const versionLabels = reactive(new Map<number, string>())
const form = reactive({ scopeType: 'product' as 'product' | 'version', productId: '', versionId: '' })

onMounted(load)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    summary.value = await listUserScopes(props.userId)
    products.value = (await listProducts({ status: 'active', pageSize: 100 })).items
    await loadScopeVersionLabels()
  } catch (caught) {
    error.value = caught instanceof ScopeApiError && caught.status === 403
      ? '无权配置产品范围'
      : '产品授权暂时不可用，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function loadScopeVersionLabels(): Promise<void> {
  const productIds = new Set(
    (summary.value?.scopes ?? [])
      .filter((scope) => scope.scope_type === 'version')
      .map((scope) => scope.product_id),
  )
  for (const productId of productIds) {
    const versions = await listVersions(productId)
    versions.forEach((version) => versionLabels.set(version.id, version.version_no))
  }
}

function scopeTypeChanged(): void {
  form.versionId = ''
  if (form.scopeType === 'version' && form.productId) void loadSelectableVersions()
}

function productChanged(): void {
  form.versionId = ''
  if (form.scopeType === 'version') void loadSelectableVersions()
}

async function loadSelectableVersions(): Promise<void> {
  if (!form.productId) {
    selectableVersions.value = []
    return
  }
  try {
    selectableVersions.value = (await listVersions(Number(form.productId))).filter((version) => version.status === 'active')
    selectableVersions.value.forEach((version) => versionLabels.set(version.id, version.version_no))
  } catch {
    selectableVersions.value = []
    actionError.value = '产品版本读取失败，请重试'
  }
}

async function submitGrant(): Promise<void> {
  if (!form.productId || (form.scopeType === 'version' && !form.versionId)) return
  submitting.value = true
  actionError.value = ''
  try {
    await grantUserScope(props.userId, {
      scope_type: form.scopeType,
      product_id: Number(form.productId),
      product_version_id: form.scopeType === 'version' ? Number(form.versionId) : null,
    })
    summary.value = await listUserScopes(props.userId)
    await loadScopeVersionLabels()
  } catch (caught) {
    actionError.value = caught instanceof ScopeApiError && caught.status === 403
      ? '无权配置产品范围'
      : '授权失败，请检查产品与版本后重试'
  } finally {
    submitting.value = false
  }
}

async function revoke(scopeId: number): Promise<void> {
  actionError.value = ''
  try {
    await revokeUserScope(props.userId, scopeId)
    summary.value = await listUserScopes(props.userId)
  } catch {
    actionError.value = '撤销失败，请刷新后重试'
  }
}

function productName(productId: number): string {
  return products.value.find((product) => product.id === productId)?.product_name ?? `产品 #${productId}`
}

function versionName(versionId: number | null): string {
  return versionId === null ? '未知版本' : versionLabels.get(versionId) ?? `版本 #${versionId}`
}
</script>

<style scoped>
.scope-editor { width: min(720px, calc(100% - 32px)); max-height: calc(100vh - 48px); overflow: auto; margin: 24px auto; padding: 30px; border-top: 5px solid var(--brand-red); background: var(--paper); box-shadow: 0 24px 80px rgba(32,36,40,.3); }
header { display: flex; justify-content: space-between; gap: 20px; }
header p { margin: 0 0 8px; color: var(--brand-red); font-size: 10px; font-weight: 900; letter-spacing: .18em; }
h2 { margin: 0; color: var(--ink); font: 700 30px/1.2 var(--font-display); }
header button { border: 0; background: transparent; font-size: 30px; cursor: pointer; }
form { display: grid; grid-template-columns: 1fr 1.4fr 1fr auto; align-items: end; gap: 12px; margin: 28px 0; padding: 18px; background: var(--paper-warm); }
label { display: grid; gap: 7px; font-size: 12px; font-weight: 800; }
select, form button { min-height: 42px; border: 1px solid var(--line-strong); padding: 0 12px; background: #fff; }
form button { border-color: var(--brand-red); color: #fff; background: var(--brand-red); font-weight: 800; cursor: pointer; }
.scope-state, .global-note { margin-top: 24px; padding: 18px; color: var(--text-muted); background: var(--paper-warm); }
.scope-state.error, .action-error { color: var(--danger); border-left: 4px solid var(--danger); }
.scope-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.scope-list li { display: flex; justify-content: space-between; gap: 18px; padding: 16px; border: 1px solid var(--line); }
.scope-list strong, .scope-list span, .scope-list small { display: block; }
.scope-list span, .scope-list small { margin-top: 5px; color: var(--text-muted); font-size: 12px; }
.scope-list li.ineffective { opacity: .72; border-style: dashed; }
.scope-list li > button { align-self: center; border: 0; color: var(--danger); background: transparent; font-weight: 800; cursor: pointer; }
.action-error { padding: 12px; }
@media (max-width: 760px) { form { grid-template-columns: 1fr; } }
</style>
