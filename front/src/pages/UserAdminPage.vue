<template>
  <main class="users-page">
    <section class="page-heading">
      <div>
        <p class="eyebrow">SYSTEM / PEOPLE</p>
        <h1>用户与角色</h1>
        <p class="heading-copy">维护内网身份、职责边界与人员状态。每次变更都保留审计轨迹。</p>
      </div>
      <button class="primary-button" data-action="create-user" type="button" @click="openCreate">
        <span aria-hidden="true">＋</span> 新建用户
      </button>
    </section>

    <section class="signal-strip" aria-label="用户统计">
      <div><strong>{{ pageData.total }}</strong><span>当前结果</span></div>
      <div><strong>{{ activeCount }}</strong><span>启用用户</span></div>
      <div><strong>3</strong><span>固定角色</span></div>
      <p><span class="signal-dot"></span>角色与状态变更将写入数据库审计</p>
    </section>

    <section class="workspace-card">
      <form class="filters" aria-label="用户筛选" @submit.prevent="loadUsers(1)">
        <label class="search-field">
          <span>检索用户</span>
          <input v-model="filters.query" type="search" placeholder="登录名或显示名称" />
        </label>
        <label>
          <span>状态</span>
          <select v-model="filters.status">
            <option value="">全部状态</option>
            <option value="active">启用</option>
            <option value="disabled">已停用</option>
          </select>
        </label>
        <label>
          <span>固定角色</span>
          <select v-model="filters.role">
            <option value="">全部角色</option>
            <option v-for="role in roleOptions" :key="role.value" :value="role.value">{{ role.label }}</option>
          </select>
        </label>
        <button class="filter-button" type="submit">应用筛选</button>
      </form>

      <div v-if="loading" class="state-block" aria-live="polite">
        <span class="loader" aria-hidden="true"></span>
        <p>正在读取用户目录…</p>
      </div>
      <div v-else-if="accessDenied" class="state-block denied" role="alert">
        <span class="state-code">403</span>
        <div><strong>无权访问用户管理</strong><p>当前身份缺少管理员角色，未返回任何用户数据。</p></div>
      </div>
      <div v-else-if="loadError" class="state-block" role="alert">
        <strong>用户目录暂时不可用</strong>
        <p>请检查服务状态后重试。</p>
        <button class="text-button" type="button" @click="loadUsers(pageData.page)">重新加载</button>
      </div>
      <div v-else-if="pageData.items.length === 0" class="state-block empty">
        <span aria-hidden="true">◎</span>
        <strong>暂无用户</strong>
        <p>当前筛选没有匹配结果，可以调整条件或新建用户。</p>
      </div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>用户</th>
              <th>固定角色</th>
              <th>状态</th>
              <th>最近登录</th>
              <th><span class="sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in pageData.items" :key="user.id">
              <td>
                <div class="user-cell">
                  <span class="avatar" aria-hidden="true">{{ initials(user.display_name) }}</span>
                  <span><strong>{{ user.display_name }}</strong><small>@{{ user.login_name }} · v{{ user.row_version }}</small></span>
                </div>
              </td>
              <td>
                <div class="role-list">
                  <span v-for="role in user.roles" :key="role" class="role-chip">{{ roleLabel(role) }}</span>
                </div>
              </td>
              <td><span class="status-badge" :class="user.status"><i></i>{{ user.status === 'active' ? '启用' : '已停用' }}</span></td>
              <td>{{ formatDate(user.last_login_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" :aria-label="`配置${user.display_name}产品授权`" @click="scopeUser = user">授权</button>
                  <button type="button" :aria-label="`编辑${user.display_name}`" @click="openEdit(user)">编辑</button>
                  <button type="button" :aria-label="`重置${user.display_name}密码`" @click="openPassword(user)">重置密码</button>
                  <button v-if="user.status === 'active'" class="danger-link" type="button" :aria-label="`停用${user.display_name}`" @click="confirmDisable(user)">停用</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer v-if="pageData.total > pageData.page_size" class="pagination">
        <span>第 {{ pageData.page }} 页 · 共 {{ pageData.total }} 人</span>
        <div>
          <button type="button" :disabled="pageData.page === 1" @click="loadUsers(pageData.page - 1)">上一页</button>
          <button type="button" :disabled="pageData.page * pageData.page_size >= pageData.total" @click="loadUsers(pageData.page + 1)">下一页</button>
        </div>
      </footer>
    </section>

    <div v-if="editor.open" class="modal-layer" @click.self="closeEditor">
      <section class="drawer" role="dialog" aria-modal="true" :aria-labelledby="editor.mode === 'create' ? 'create-title' : 'edit-title'">
        <header>
          <div>
            <p class="eyebrow">{{ editor.mode === 'create' ? 'NEW IDENTITY' : 'EDIT IDENTITY' }}</p>
            <h2 :id="editor.mode === 'create' ? 'create-title' : 'edit-title'">{{ editor.mode === 'create' ? '新建用户' : '编辑用户' }}</h2>
          </div>
          <button class="close-button" type="button" aria-label="关闭" @click="closeEditor">×</button>
        </header>
        <form data-form="user-editor" @submit.prevent="submitEditor">
          <label v-if="editor.mode === 'create'">
            <span>登录名</span>
            <input v-model.trim="editor.loginName" name="login_name" autocomplete="off" maxlength="64" required />
            <small>创建后作为稳定身份标识使用</small>
          </label>
          <label>
            <span>显示名称</span>
            <input v-model.trim="editor.displayName" name="display_name" maxlength="100" required />
          </label>
          <label v-if="editor.mode === 'create'">
            <span>初始密码</span>
            <input v-model="editor.password" name="password" type="password" autocomplete="new-password" required />
            <small>密码不会出现在响应与审计记录中</small>
          </label>
          <fieldset>
            <legend>固定角色</legend>
            <label v-for="role in roleOptions" :key="role.value" class="role-option">
              <input v-model="editor.roles" name="roles" type="checkbox" :value="role.value" />
              <span><b>{{ role.label }}</b><small>{{ role.description }}</small></span>
            </label>
          </fieldset>
          <p v-if="editor.error" class="form-error" role="alert">{{ editor.error }}</p>
          <div v-if="editor.conflict" class="conflict-note" data-state="conflict">
            <strong>数据已被其他管理员更新</strong>
            <p>已读取最新版本，但保留了你尚未保存的输入。确认差异后可以再次提交。</p>
          </div>
          <footer>
            <button class="secondary-button" type="button" @click="closeEditor">取消</button>
            <button class="primary-button" type="submit" :disabled="editor.submitting">
              {{ editor.submitting ? '正在提交…' : editor.mode === 'create' ? '创建用户' : '保存修改' }}
            </button>
          </footer>
        </form>
      </section>
    </div>

    <div v-if="scopeUser" class="modal-layer" @click.self="scopeUser = null">
      <ProductScopeEditor
        :user-id="scopeUser.id"
        :user-display-name="scopeUser.display_name"
        @close="scopeUser = null"
      />
    </div>

    <div v-if="passwordDialog.open" class="modal-layer" @click.self="passwordDialog.open = false">
      <section class="compact-dialog" role="dialog" aria-modal="true" aria-labelledby="password-title">
        <p class="eyebrow">CREDENTIAL RESET</p>
        <h2 id="password-title">重置 {{ passwordDialog.user?.display_name }} 的密码</h2>
        <form @submit.prevent="submitPassword">
          <label><span>新密码</span><input v-model="passwordDialog.password" type="password" autocomplete="new-password" required /></label>
          <p v-if="passwordDialog.error" class="form-error" role="alert">{{ passwordDialog.error }}</p>
          <footer><button class="secondary-button" type="button" @click="passwordDialog.open = false">取消</button><button class="primary-button" type="submit">确认重置</button></footer>
        </form>
      </section>
    </div>

    <div v-if="disableDialog.open" class="modal-layer" @click.self="disableDialog.open = false">
      <section class="compact-dialog warning-dialog" role="dialog" aria-modal="true" aria-labelledby="disable-title">
        <span class="warning-mark" aria-hidden="true">!</span>
        <h2 id="disable-title">停用 {{ disableDialog.user?.display_name }}？</h2>
        <p>停用后将保留全部历史记录、角色与操作轨迹。按照当前认证基线，停用状态不作为登录附加校验。</p>
        <p v-if="disableDialog.error" class="form-error" role="alert">{{ disableDialog.error }}</p>
        <footer><button class="secondary-button" type="button" @click="disableDialog.open = false">取消</button><button class="danger-button" type="button" @click="submitDisable">确认停用</button></footer>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import ProductScopeEditor from '../components/ProductScopeEditor.vue'

import {
  createUser,
  disableUser,
  getUser,
  listUsers,
  resetUserPassword,
  updateUser,
  UserApiError,
  type ManagedUser,
  type UserPage,
  type UserRole,
} from '../api/users'

const roleOptions: Array<{ value: UserRole; label: string; description: string }> = [
  { value: 'admin', label: '系统管理员', description: '维护账号、主数据与全局配置' },
  { value: 'product_owner', label: '产品负责人', description: '评估所负责产品版本的漏洞' },
  { value: 'reviewer', label: '审核人', description: '审核评估并确认 EOL 信息' },
]

const filters = reactive({ query: '', status: '', role: '' })
const pageData = reactive<UserPage>({ items: [], total: 0, page: 1, page_size: 20 })
const loading = ref(true)
const accessDenied = ref(false)
const loadError = ref(false)
const activeCount = computed(() => pageData.items.filter((user) => user.status === 'active').length)
const scopeUser = ref<ManagedUser | null>(null)

const editor = reactive({
  open: false,
  mode: 'create' as 'create' | 'edit',
  userId: 0,
  loginName: '',
  displayName: '',
  password: '',
  roles: [] as UserRole[],
  rowVersion: 1,
  submitting: false,
  error: '',
  conflict: false,
})
const passwordDialog = reactive({ open: false, user: null as ManagedUser | null, password: '', error: '' })
const disableDialog = reactive({ open: false, user: null as ManagedUser | null, error: '' })

onMounted(() => loadUsers(1))

async function loadUsers(page: number): Promise<void> {
  loading.value = true
  accessDenied.value = false
  loadError.value = false
  try {
    const result = await listUsers({ ...filters, page, pageSize: pageData.page_size })
    Object.assign(pageData, result)
  } catch (error) {
    accessDenied.value = error instanceof UserApiError && error.code === 'AUTH_FORBIDDEN'
    loadError.value = !accessDenied.value
    pageData.items = []
    pageData.total = 0
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  Object.assign(editor, { open: true, mode: 'create', userId: 0, loginName: '', displayName: '', password: '', roles: [], rowVersion: 1, error: '', conflict: false })
}

function openEdit(user: ManagedUser): void {
  Object.assign(editor, { open: true, mode: 'edit', userId: user.id, loginName: user.login_name, displayName: user.display_name, password: '', roles: [...user.roles], rowVersion: user.row_version, error: '', conflict: false })
}

function closeEditor(): void {
  editor.open = false
}

async function submitEditor(): Promise<void> {
  if (editor.roles.length === 0) {
    editor.error = '请至少选择一个固定角色'
    return
  }
  editor.submitting = true
  editor.error = ''
  editor.conflict = false
  try {
    const saved = editor.mode === 'create'
      ? await createUser({ login_name: editor.loginName, display_name: editor.displayName, password: editor.password, roles: editor.roles })
      : await updateUser(editor.userId, { display_name: editor.displayName, roles: editor.roles, row_version: editor.rowVersion })
    replaceUser(saved, editor.mode === 'create')
    closeEditor()
  } catch (error) {
    if (error instanceof UserApiError && error.code === 'USER_VERSION_CONFLICT') {
      editor.conflict = true
      const latest = await getUser(editor.userId).catch(() => null)
      if (latest) editor.rowVersion = latest.row_version
    } else if (error instanceof UserApiError && error.code === 'USER_LOGIN_NAME_CONFLICT') {
      editor.error = '该登录名已存在，请更换后重试'
    } else {
      editor.error = '保存失败，请检查输入或稍后重试'
    }
  } finally {
    editor.submitting = false
  }
}

function openPassword(user: ManagedUser): void {
  Object.assign(passwordDialog, { open: true, user, password: '', error: '' })
}

async function submitPassword(): Promise<void> {
  if (!passwordDialog.user) return
  try {
    const saved = await resetUserPassword(passwordDialog.user.id, { password: passwordDialog.password, row_version: passwordDialog.user.row_version })
    replaceUser(saved)
    passwordDialog.open = false
  } catch (error) {
    passwordDialog.error = error instanceof UserApiError && error.code === 'USER_VERSION_CONFLICT'
      ? '数据版本已变化，请关闭后重新操作'
      : '密码重置失败，请稍后重试'
  }
}

function confirmDisable(user: ManagedUser): void {
  Object.assign(disableDialog, { open: true, user, error: '' })
}

async function submitDisable(): Promise<void> {
  if (!disableDialog.user) return
  try {
    const saved = await disableUser(disableDialog.user.id, { row_version: disableDialog.user.row_version })
    replaceUser(saved)
    disableDialog.open = false
  } catch (error) {
    disableDialog.error = error instanceof UserApiError && error.code === 'USER_VERSION_CONFLICT'
      ? '数据版本已变化，请刷新后重试'
      : '停用失败，请稍后重试'
  }
}

function replaceUser(user: ManagedUser, prepend = false): void {
  const index = pageData.items.findIndex((item) => item.id === user.id)
  if (index >= 0) pageData.items.splice(index, 1, user)
  else if (prepend) {
    pageData.items.unshift(user)
    pageData.total += 1
  }
}

function roleLabel(role: string): string {
  return roleOptions.find((item) => item.value === role)?.label ?? role
}

function initials(name: string): string {
  return name.trim().slice(0, 2)
}

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '尚未登录'
}
</script>

<style scoped>
.users-page { max-width: 1480px; margin: 0 auto; padding: 48px clamp(24px, 4vw, 64px) 72px; }
.page-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 34px; animation: rise .55s ease both; }
.eyebrow { margin: 0 0 9px; color: var(--amber-dark); font: 800 11px/1 var(--font-body); letter-spacing: .2em; }
h1 { margin: 0; color: var(--ink); font: 700 clamp(40px, 5vw, 64px)/.98 var(--font-display); letter-spacing: -.035em; }
.heading-copy { max-width: 560px; margin: 15px 0 0; color: var(--text-muted); line-height: 1.8; }
button, input, select { font: inherit; }
.primary-button, .secondary-button, .danger-button, .filter-button { min-height: 44px; padding: 0 19px; border: 1px solid transparent; font-weight: 800; cursor: pointer; transition: transform .18s, box-shadow .18s, background .18s; }
.primary-button { border-radius: 4px; background: var(--brand-red); color: #fff; box-shadow: 0 8px 18px rgba(215, 25, 32, .18); }
.primary-button:hover { transform: translateY(-2px); background: var(--brand-red-deep); box-shadow: 0 12px 22px rgba(168, 15, 24, .22); }
.secondary-button { color: var(--forest); border-color: var(--line-strong); background: transparent; }
.danger-button { color: #fff; background: var(--danger); }
.signal-strip { display: grid; grid-template-columns: repeat(3, minmax(100px, 150px)) 1fr; border: 1px solid var(--line); background: rgba(255, 255, 255, .82); margin-bottom: 18px; animation: rise .55s .08s ease both; }
.signal-strip > div { display: flex; align-items: baseline; gap: 9px; padding: 18px 20px; border-right: 1px solid var(--line); }
.signal-strip strong { color: var(--ink); font: 700 26px/1 var(--font-display); }
.signal-strip span, .signal-strip p { color: var(--text-muted); font-size: 12px; }
.signal-strip p { display: flex; align-items: center; justify-content: flex-end; gap: 9px; margin: 0; padding: 0 20px; }
.signal-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 0 4px rgba(22, 132, 91, .12); }
.workspace-card { border: 1px solid var(--line-strong); background: var(--paper); box-shadow: var(--shadow-card); animation: rise .55s .15s ease both; }
.filters { display: grid; grid-template-columns: minmax(260px, 1fr) 180px 190px auto; gap: 14px; align-items: end; padding: 22px; border-bottom: 1px solid var(--line); background: var(--paper-warm); }
.filters label, .drawer form > label, .compact-dialog label { display: grid; gap: 7px; color: var(--ink-soft); font-size: 12px; font-weight: 800; }
input, select { width: 100%; min-height: 44px; box-sizing: border-box; border: 1px solid var(--line-strong); border-radius: 4px; background: #fff; color: var(--ink); padding: 0 13px; outline: none; }
input:focus, select:focus { border-color: var(--brand-red); box-shadow: 0 0 0 3px rgba(215, 25, 32, .1); }
.filter-button { background: var(--ink); color: var(--paper); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 900px; }
th { padding: 14px 18px; border-bottom: 1px solid var(--line-strong); color: var(--text-muted); background: #f5f6f7; font-size: 11px; letter-spacing: .1em; text-align: left; }
td { padding: 17px 18px; border-bottom: 1px solid var(--line); color: var(--ink-soft); vertical-align: middle; }
tbody tr { transition: background .18s; }
tbody tr:hover { background: rgba(215, 25, 32, .035); }
.user-cell { display: flex; align-items: center; gap: 12px; }
.avatar { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 4px; background: var(--brand-red); color: var(--paper); font: 700 13px var(--font-display); box-shadow: 3px 3px 0 rgba(215, 25, 32, .16); }
.user-cell strong { display: block; color: var(--ink); }
.user-cell small { display: block; margin-top: 4px; color: var(--text-muted); }
.role-list { display: flex; flex-wrap: wrap; gap: 6px; }
.role-chip { padding: 4px 8px; border: 1px solid #efc5c8; border-radius: 3px; background: #fff3f4; color: var(--brand-red-deep); font-size: 11px; font-weight: 800; }
.status-badge { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 800; }
.status-badge i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.status-badge.active { color: var(--success); }
.status-badge.disabled { color: var(--text-muted); }
.row-actions { display: flex; justify-content: flex-end; gap: 12px; white-space: nowrap; }
.row-actions button, .text-button { border: 0; background: none; padding: 3px; color: var(--forest); font-size: 12px; font-weight: 800; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
.row-actions .danger-link { color: var(--danger); }
.state-block { min-height: 320px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; text-align: center; color: var(--text-muted); }
.state-block p { margin: 0; }
.state-block.empty > span { font: 700 54px var(--font-display); color: var(--amber); }
.state-block.denied { flex-direction: row; text-align: left; }
.state-code { font: 700 68px var(--font-display); color: rgba(154, 62, 46, .24); }
.loader { width: 28px; height: 28px; border: 2px solid var(--line); border-top-color: var(--forest); border-radius: 50%; animation: spin .7s linear infinite; }
.pagination { display: flex; justify-content: space-between; padding: 18px 22px; color: var(--text-muted); font-size: 12px; }
.pagination button { border: 1px solid var(--line); background: transparent; padding: 7px 12px; }
.modal-layer { position: fixed; inset: 0; z-index: 50; display: flex; justify-content: flex-end; background: rgba(20, 24, 28, .48); backdrop-filter: blur(3px); }
.drawer { width: min(520px, 100%); min-height: 100%; overflow-y: auto; background: var(--paper); box-shadow: -16px 0 60px rgba(32, 36, 40, .18); animation: slide-in .3s ease both; }
.drawer > header { display: flex; justify-content: space-between; padding: 34px 34px 24px; border-bottom: 1px solid var(--line); }
.drawer h2, .compact-dialog h2 { margin: 0; color: var(--ink); font: 700 32px/1.15 var(--font-display); }
.close-button { border: 0; background: none; color: var(--ink); font-size: 30px; cursor: pointer; }
.drawer form { display: grid; gap: 22px; padding: 30px 34px; }
.drawer small { color: var(--text-muted); font-weight: 400; }
fieldset { display: grid; gap: 9px; border: 0; padding: 0; margin: 0; }
legend { margin-bottom: 10px; color: var(--ink-soft); font-size: 12px; font-weight: 800; }
.role-option { display: flex; gap: 12px; align-items: flex-start; padding: 13px; border: 1px solid var(--line); cursor: pointer; }
.role-option:has(input:checked) { border-color: var(--brand-red); background: #fff3f4; }
.role-option input { width: 17px; min-height: 17px; margin: 3px 0 0; accent-color: var(--forest); }
.role-option b, .role-option small { display: block; }
.role-option small { margin-top: 3px; }
.drawer footer, .compact-dialog footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
.form-error { margin: 0; color: var(--danger); font-weight: 800; }
.conflict-note { padding: 14px; border-left: 4px solid var(--brand-red); background: #fff1f2; color: var(--ink); }
.conflict-note p { margin: 5px 0 0; color: var(--text-muted); line-height: 1.6; }
.compact-dialog { width: min(460px, calc(100% - 36px)); margin: auto; padding: 34px; border-top: 5px solid var(--brand-red); background: var(--paper); box-shadow: 0 24px 80px rgba(32, 36, 40, .3); animation: rise .25s ease both; }
.compact-dialog form { display: grid; gap: 20px; margin-top: 24px; }
.warning-dialog { position: relative; }
.warning-dialog > p { color: var(--text-muted); line-height: 1.7; }
.warning-mark { display: grid; place-items: center; width: 36px; height: 36px; margin-bottom: 16px; background: var(--danger); color: white; font-weight: 900; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@keyframes rise { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes slide-in { from { transform: translateX(100%); } to { transform: none; } }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) {
  .page-heading { align-items: flex-start; flex-direction: column; }
  .signal-strip { grid-template-columns: repeat(3, 1fr); }
  .signal-strip p { display: none; }
  .filters { grid-template-columns: 1fr 1fr; }
  .search-field { grid-column: 1 / -1; }
}
@media (max-width: 560px) {
  .users-page { padding-inline: 16px; }
  .signal-strip { grid-template-columns: 1fr; }
  .signal-strip > div { border-right: 0; border-bottom: 1px solid var(--line); }
  .filters { grid-template-columns: 1fr; }
  .drawer form, .drawer > header { padding-inline: 22px; }
}
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
</style>
