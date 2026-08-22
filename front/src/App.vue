<template>
  <div class="app-root" :class="{ 'public-view': isPublicView }">
    <aside v-if="!isPublicView" class="app-sidebar">
      <a class="brand-lockup" href="/system" aria-label="OTS 信息维护平台首页" @click.prevent="router.push('/system')">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="brand-copy"><strong>OTS</strong><small>信息维护平台</small></span>
      </a>
      <nav aria-label="主导航">
        <RouterLink to="/system"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6v-9h-6v9Zm0-16v5h6V4h-6Z" /></svg><span>工作台</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/system/products"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 4h16v16H4zM8 8h8v2H8zm0 4h8v2H8zm0 4h5v2H8z" /></svg><span>产品管理</span></RouterLink>
        <RouterLink v-if="hasScopedProducts" to="/system/my-products"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 4h16v16H4zM8 8h8v2H8zm0 4h8v2H8zm0 4h5v2H8z" /></svg><span>我的产品</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/system/ots"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.8 8 12 11.7 5.2 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z" /></svg><span>OTS</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/system/data-exchange/collector-scope"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 4h16v4H4V4Zm0 6h16v10H4V10Zm3 3v2h6v-2H7Zm0 4v1h10v-1H7Z" /></svg><span>采集范围</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/system/data-exchange/import-packages"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 2 3 6v12l9 4 9-4V6l-9-4Zm0 2.2L17.4 6 12 7.8 6.6 6 12 4.2ZM5 8.1l6 2v9.2l-6-2.7V8.1Zm8 11.2v-9.2l6-2v8.5l-6 2.7Zm-1-7.8 3-1v2.2l-2 .7v3l-2 .7v-5.3l1-.3Z" /></svg><span>数据包导入</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/system/users"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3Zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3Zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5C15 14.17 10.33 13 8 13Zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5Z" /></svg><span>用户与角色</span></RouterLink>
        <RouterLink to="/health"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 13h4l2-6 4 12 2-6h6v-2h-4.56L13 21.32 9 9.32 8.44 11H3v2Z" /></svg><span>运行状态</span></RouterLink>
      </nav>
      <div v-if="authentication.user" class="sidebar-account">
        <div class="identity-chip">
          <span>{{ authentication.user.display_name.slice(0, 1) }}</span>
          <div><strong>{{ authentication.user.display_name }}</strong><small>{{ primaryRole }}</small></div>
        </div>
        <button type="button" aria-label="退出登录" :disabled="loggingOut" @click="signOut">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M10 17v2H5V5h5v2h2V3H3v18h9v-4h-2Zm9-6h-7v2h7v3l4-4-4-4v3Z" /></svg>
          <span>{{ loggingOut ? '正在退出…' : '退出登录' }}</span>
        </button>
      </div>
    </aside>
    <div class="app-content">
      <p v-if="authentication.feedback" class="global-feedback" role="alert">{{ authentication.feedback }}</p>
      <RouterView />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { logout } from './api/auth'
import { authentication, clearAuthenticatedUser } from './auth'

const route = useRoute()
const router = useRouter()
const loggingOut = ref(false)
const isPublicView = computed(() => route.path === '/login')
const roleNames: Record<string, string> = { admin: '系统管理员', product_owner: '产品负责人', reviewer: '审核人' }
const primaryRole = computed(() => roleNames[authentication.user?.roles[0] ?? ''] ?? '已认证用户')
const isAdmin = computed(() => authentication.user?.roles.includes('admin') ?? false)
const hasScopedProducts = computed(() => !isAdmin.value && (authentication.scope?.effective_product_ids.length ?? 0) > 0)

async function signOut(): Promise<void> {
  if (loggingOut.value) return
  loggingOut.value = true
  authentication.feedback = ''
  try {
    await logout()
    clearAuthenticatedUser()
    await router.replace('/login')
  } catch {
    authentication.feedback = '退出失败，请检查网络后重试'
  } finally {
    loggingOut.value = false
  }
}
</script>

<style>
:root {
  --brand-red: #d71920;
  --brand-red-deep: #a80f18;
  --ink: #202428;
  --ink-soft: #3e464d;
  --forest: var(--brand-red);
  --forest-deep: #202428;
  --paper: #ffffff;
  --paper-warm: #f7f8fa;
  --canvas: #f4f6f8;
  --amber: var(--brand-red);
  --amber-dark: var(--brand-red-deep);
  --danger: #b4232a;
  --success: #16845b;
  --text-muted: #69737d;
  --line: #dde1e5;
  --line-strong: #b8c0c7;
  --shadow-card: 0 14px 38px rgba(32, 36, 40, .08);
  --font-display: "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  --font-body: "Microsoft YaHei UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
  font-family: var(--font-body);
  color: var(--ink-soft);
  background: var(--canvas);
  font-synthesis: none;
}
* { box-sizing: border-box; }
html { min-width: 320px; background: var(--canvas); }
body { min-width: 320px; min-height: 100vh; margin: 0; background: var(--canvas); }
button, input, select { font-family: var(--font-body); }
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid rgba(215, 25, 32, .28); outline-offset: 3px; }
a { color: inherit; }
.app-root { min-height: 100vh; padding-left: 240px; }
.app-root.public-view { padding-left: 0; }
.app-sidebar { position: fixed; inset: 0 auto 0 0; z-index: 30; width: 240px; display: flex; flex-direction: column; color: #fff; background: #202428; box-shadow: 8px 0 30px rgba(20, 24, 28, .12); }
.brand-lockup { min-height: 92px; display: flex; align-items: center; gap: 12px; padding: 0 25px; border-bottom: 1px solid rgba(255, 255, 255, .11); text-decoration: none; }
.brand-mark { width: 35px; height: 35px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; padding: 6px; border-radius: 4px; background: var(--brand-red); transform: skewX(-6deg); }
.brand-mark i { display: block; background: #fff; opacity: .95; }
.brand-lockup strong, .brand-lockup small { display: block; }
.brand-lockup strong { font-size: 21px; font-weight: 800; line-height: 1; letter-spacing: .08em; }
.brand-lockup small { margin-top: 5px; color: rgba(255,255,255,.56); font-size: 10px; letter-spacing: .14em; }
.app-sidebar nav { display: grid; gap: 6px; padding: 24px 14px; }
.app-sidebar nav a { min-height: 48px; display: flex; align-items: center; gap: 13px; padding: 0 14px; border-radius: 5px; color: rgba(255,255,255,.68); font-size: 13px; font-weight: 700; text-decoration: none; transition: color .18s, background .18s, transform .18s; }
.app-sidebar nav a:hover { color: #fff; background: rgba(255,255,255,.07); transform: translateX(2px); }
.app-sidebar nav a.router-link-active { color: #fff; background: var(--brand-red); box-shadow: 0 7px 18px rgba(215,25,32,.24); }
.app-sidebar svg { width: 19px; height: 19px; flex: 0 0 auto; fill: currentColor; }
.sidebar-account { margin-top: auto; padding: 18px 14px; border-top: 1px solid rgba(255,255,255,.11); }
.identity-chip { display: flex; align-items: center; gap: 11px; padding: 4px 6px 16px; }
.identity-chip > span { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 auto; border-radius: 50%; color: #fff; background: var(--brand-red); font-size: 14px; font-weight: 800; }
.identity-chip strong, .identity-chip small { display: block; max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.identity-chip strong { color: #fff; font-size: 12px; }
.identity-chip small { margin-top: 3px; color: rgba(255,255,255,.48); font-size: 10px; }
.sidebar-account button { width: 100%; min-height: 40px; display: flex; align-items: center; gap: 11px; border: 1px solid rgba(255,255,255,.13); border-radius: 4px; padding: 0 12px; color: rgba(255,255,255,.68); background: transparent; font-size: 12px; font-weight: 700; cursor: pointer; }
.sidebar-account button:hover:not(:disabled) { color: #fff; border-color: rgba(255,255,255,.3); background: rgba(255,255,255,.06); }
.sidebar-account button:disabled { opacity: .55; cursor: wait; }
.app-content { min-width: 0; min-height: 100vh; }
.global-feedback { margin: 0; padding: 12px 20px; border-bottom: 1px solid #f0bcc0; background: #fff1f2; color: var(--brand-red-deep); text-align: center; font-size: 13px; font-weight: 700; }
@media (max-width: 780px) {
  .app-root { padding-left: 82px; }
  .app-root.public-view { padding-left: 0; }
  .app-sidebar { width: 82px; }
  .brand-lockup { min-height: 80px; justify-content: center; padding: 0; }
  .brand-copy, .app-sidebar nav a span, .identity-chip div, .sidebar-account button span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .app-sidebar nav { padding-inline: 10px; }
  .app-sidebar nav a { justify-content: center; padding: 0; }
  .identity-chip { justify-content: center; padding-inline: 0; }
  .sidebar-account button { justify-content: center; padding: 0; }
}
@media (prefers-reduced-motion: reduce) { .app-sidebar nav a { transition: none; } }
</style>
