<template>
  <div class="app-root" :class="{ 'public-view': isPublicView }">
    <header v-if="!isPublicView" class="platform-shell">
      <RouterLink class="brand-lockup" to="/system" aria-label="OTS 信息维护平台首页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span><strong>OTS</strong><small>信息维护平台</small></span>
      </RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/system">工作台</RouterLink>
        <RouterLink v-if="isAdmin" to="/system/users">用户与角色</RouterLink>
        <RouterLink to="/health">运行状态</RouterLink>
      </nav>
      <div v-if="authentication.user" class="identity-chip">
        <span>{{ authentication.user.display_name.slice(0, 1) }}</span>
        <div><strong>{{ authentication.user.display_name }}</strong><small>{{ primaryRole }}</small></div>
      </div>
    </header>
    <p v-if="authentication.feedback" class="global-feedback" role="alert">{{ authentication.feedback }}</p>
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { authentication } from './auth'

const route = useRoute()
const isPublicView = computed(() => route.path === '/login')
const isAdmin = computed(() => authentication.user?.roles.includes('admin') ?? false)
const roleNames: Record<string, string> = { admin: '系统管理员', product_owner: '产品负责人', reviewer: '审核人' }
const primaryRole = computed(() => roleNames[authentication.user?.roles[0] ?? ''] ?? '已认证用户')
</script>

<style>
:root {
  --ink: #142a24;
  --ink-soft: #30473f;
  --forest: #184e3f;
  --forest-deep: #0c3027;
  --paper: #fffdf7;
  --paper-warm: #f5efe3;
  --canvas: #e8e1d3;
  --amber: #d5982f;
  --amber-dark: #986316;
  --danger: #9a3e2e;
  --success: #2c7956;
  --text-muted: #6f756e;
  --line: #d8d1c3;
  --line-strong: #9fa99f;
  --shadow-card: 8px 9px 0 rgba(20, 42, 36, .13);
  --font-display: "STSong", "Songti SC", "Noto Serif CJK SC", Georgia, serif;
  --font-body: "Microsoft YaHei UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
  font-family: var(--font-body);
  color: var(--ink-soft);
  background: var(--canvas);
  font-synthesis: none;
}

* { box-sizing: border-box; }
html { min-width: 320px; background: var(--canvas); }
body { min-width: 320px; min-height: 100vh; margin: 0; background-color: var(--canvas); background-image: linear-gradient(rgba(24, 78, 63, .045) 1px, transparent 1px), linear-gradient(90deg, rgba(24, 78, 63, .045) 1px, transparent 1px); background-size: 32px 32px; }
button, input, select { font-family: var(--font-body); }
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid rgba(213, 152, 47, .45); outline-offset: 3px; }
a { color: inherit; }
.app-root { min-height: 100vh; }
.platform-shell { position: sticky; top: 0; z-index: 30; min-height: 74px; display: grid; grid-template-columns: 250px 1fr auto; align-items: stretch; border-bottom: 1px solid #82938a; background: rgba(247, 243, 233, .94); backdrop-filter: blur(12px); }
.brand-lockup { display: flex; align-items: center; gap: 12px; padding: 0 24px; border-right: 1px solid var(--line); text-decoration: none; }
.brand-mark { width: 30px; height: 30px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; padding: 5px; background: var(--forest); transform: rotate(-3deg); }
.brand-mark i { display: block; background: var(--amber); }
.brand-lockup strong, .brand-lockup small { display: block; }
.brand-lockup strong { color: var(--forest); font: 800 21px/1 var(--font-display); letter-spacing: .08em; }
.brand-lockup small { margin-top: 3px; color: var(--text-muted); font-size: 10px; letter-spacing: .16em; }
.platform-shell nav { display: flex; align-items: stretch; }
.platform-shell nav a { display: flex; align-items: center; padding: 0 22px; color: var(--ink-soft); font-size: 13px; font-weight: 800; text-decoration: none; border-right: 1px solid transparent; border-left: 1px solid transparent; }
.platform-shell nav a:hover { background: rgba(24, 78, 63, .05); }
.platform-shell nav a.router-link-active { color: var(--forest); background: rgba(24, 78, 63, .08); border-color: var(--line); box-shadow: inset 0 -3px var(--amber); }
.identity-chip { display: flex; align-items: center; gap: 10px; padding: 0 24px; border-left: 1px solid var(--line); }
.identity-chip > span { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: var(--paper); background: var(--forest); font: 700 14px var(--font-display); }
.identity-chip strong, .identity-chip small { display: block; white-space: nowrap; }
.identity-chip strong { color: var(--ink); font-size: 12px; }
.identity-chip small { margin-top: 3px; color: var(--text-muted); font-size: 10px; }
.global-feedback { margin: 0; padding: 12px 20px; background: #fbf0d6; color: var(--ink); text-align: center; }
@media (max-width: 780px) {
  .platform-shell { grid-template-columns: 1fr auto; }
  .platform-shell nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 40; min-height: 58px; justify-content: space-around; background: var(--paper); border-top: 1px solid var(--line-strong); }
  .platform-shell nav a { padding: 0 12px; border: 0; }
  .identity-chip { padding: 0 14px; }
  .identity-chip div { display: none; }
}
</style>
