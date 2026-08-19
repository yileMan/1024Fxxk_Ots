<template>
  <main class="login-page">
    <section class="brand-panel" aria-label="平台简介">
      <div class="panel-grid" aria-hidden="true"></div>
      <header>
        <span class="login-brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <div><strong>OTS</strong><small>INFORMATION MAINTENANCE</small></div>
      </header>
      <div class="brand-copy">
        <p class="eyebrow">内网可信工作台 / 01</p>
        <h2>让每一项<br />开源组件决策<br /><em>有据可循。</em></h2>
        <p>聚合离线漏洞事实、产品评估与审核轨迹，在清晰的职责边界内完成维护闭环。</p>
      </div>
      <footer>
        <span><i></i>INTRANET ONLY</span>
        <span>V1.0 / LOCAL ACCESS</span>
      </footer>
    </section>

    <section class="login-panel">
      <div class="access-rule"><span>访问边界</span><strong>仅限组织内网授权人员</strong></div>
      <div class="login-card">
        <p class="eyebrow">IDENTITY CHECK / 02</p>
        <h1>登录 OTS 信息维护平台</h1>
        <p class="form-intro">使用本地账号进入维护平台。身份用于后续权限判断与操作审计。</p>
        <p v-if="authentication.feedback" class="feedback" role="alert">{{ authentication.feedback }}</p>
        <form @submit.prevent="submit">
          <label>
            <span>登录名</span>
            <input v-model="loginName" name="login_name" autocomplete="username" placeholder="输入本地登录名" required />
          </label>
          <label>
            <span>密码</span>
            <input v-model="password" name="password" type="password" autocomplete="current-password" placeholder="输入密码" required />
          </label>
          <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
          <button type="submit" :disabled="submitting" aria-label="登录">
            <span>{{ submitting ? '正在核验身份…' : '进入维护平台' }}</span><b aria-hidden="true">↗</b>
          </button>
        </form>
        <div class="security-note"><span aria-hidden="true">◆</span><p>账号凭据仅用于本地校验<br /><small>平台不会主动访问互联网</small></p></div>
      </div>
      <p class="version-line">OTS PLATFORM · BUILD 2026.08</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { AuthenticationError, login } from '../api/auth'
import { authentication, setAuthenticatedUser } from '../auth'

const route = useRoute()
const router = useRouter()
const loginName = ref('')
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)

async function submit(): Promise<void> {
  submitting.value = true
  errorMessage.value = ''
  try {
    const user = await login(loginName.value, password.value)
    setAuthenticatedUser(user)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/system'
    await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/system')
  } catch (error) {
    errorMessage.value = error instanceof AuthenticationError && error.code === 'AUTH_INVALID_CREDENTIALS'
      ? '账号或密码错误'
      : '登录服务暂时不可用'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: minmax(420px, 1.08fr) minmax(420px, .92fr); background: var(--paper); }
.brand-panel { position: relative; min-height: 100vh; overflow: hidden; display: flex; flex-direction: column; padding: 42px clamp(38px, 6vw, 84px); color: #f8f1df; background: var(--forest-deep); }
.brand-panel::after { content: ""; position: absolute; width: 340px; height: 340px; right: -120px; bottom: 10%; border: 1px solid rgba(213, 152, 47, .45); border-radius: 50%; box-shadow: 0 0 0 64px rgba(213, 152, 47, .035), 0 0 0 128px rgba(213, 152, 47, .025); }
.panel-grid { position: absolute; inset: 0; opacity: .12; background-image: linear-gradient(rgba(255,255,255,.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.3) 1px, transparent 1px); background-size: 52px 52px; mask-image: linear-gradient(to bottom right, black, transparent 75%); }
.brand-panel header, .brand-copy, .brand-panel footer { position: relative; z-index: 1; }
.brand-panel header { display: flex; align-items: center; gap: 14px; }
.login-brand-mark { width: 40px; height: 40px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; padding: 7px; border: 1px solid rgba(248, 241, 223, .45); transform: rotate(-3deg); }
.login-brand-mark i { background: var(--amber); }
.brand-panel header strong, .brand-panel header small { display: block; }
.brand-panel header strong { font: 800 25px/1 var(--font-display); letter-spacing: .12em; }
.brand-panel header small { margin-top: 5px; color: rgba(248, 241, 223, .62); font-size: 9px; letter-spacing: .18em; }
.brand-copy { margin: auto 0; max-width: 620px; padding: 80px 0; }
.eyebrow { margin: 0 0 18px; color: var(--amber); font-size: 11px; font-weight: 900; letter-spacing: .21em; }
.brand-copy h2 { margin: 0; font: 700 clamp(46px, 5.6vw, 78px)/1.12 var(--font-display); letter-spacing: -.045em; }
.brand-copy h2 em { color: var(--amber); font-style: normal; }
.brand-copy > p:last-child { max-width: 480px; margin: 28px 0 0; color: rgba(248, 241, 223, .68); line-height: 1.9; }
.brand-panel footer { display: flex; justify-content: space-between; color: rgba(248, 241, 223, .55); font-size: 9px; letter-spacing: .17em; }
.brand-panel footer span:first-child { display: flex; align-items: center; gap: 8px; }
.brand-panel footer i { width: 7px; height: 7px; border-radius: 50%; background: #71bf85; box-shadow: 0 0 0 4px rgba(113, 191, 133, .13); }
.login-panel { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; padding: 64px clamp(32px, 6vw, 88px); background: var(--paper); }
.login-panel::before { content: ""; position: absolute; inset: 0; pointer-events: none; background: radial-gradient(circle at 75% 12%, rgba(213, 152, 47, .11), transparent 24%); }
.access-rule { position: absolute; top: 34px; right: 42px; display: grid; gap: 4px; text-align: right; }
.access-rule span { color: var(--amber-dark); font-size: 9px; font-weight: 900; letter-spacing: .18em; }
.access-rule strong { color: var(--text-muted); font-size: 10px; }
.login-card { position: relative; z-index: 1; width: min(100%, 460px); animation: login-rise .65s cubic-bezier(.2,.8,.2,1) both; }
.login-card h1 { margin: 0; color: var(--ink); font: 700 clamp(36px, 4vw, 52px)/1.08 var(--font-display); letter-spacing: -.04em; }
.form-intro { margin: 18px 0 34px; color: var(--text-muted); line-height: 1.8; }
form { display: grid; gap: 20px; }
label { display: grid; gap: 9px; color: var(--ink); font-size: 12px; font-weight: 900; }
input { width: 100%; min-height: 54px; border: 1px solid var(--line-strong); border-radius: 0; background: #fffef9; padding: 0 16px; color: var(--ink); font: 500 15px var(--font-body); outline: none; transition: border .18s, box-shadow .18s; }
input:focus { border-color: var(--forest); box-shadow: 4px 4px 0 rgba(24, 78, 63, .12); }
input::placeholder { color: #9a9e97; }
form button { min-height: 58px; display: flex; justify-content: space-between; align-items: center; border: 0; padding: 0 20px; color: #fffdf7; background: var(--forest); font-size: 14px; font-weight: 900; cursor: pointer; box-shadow: 6px 6px 0 var(--amber); transition: transform .18s, box-shadow .18s; }
form button:hover:not(:disabled) { transform: translate(-2px,-2px); box-shadow: 9px 9px 0 var(--amber); }
form button:disabled { opacity: .65; cursor: wait; }
form button b { font-size: 21px; font-weight: 400; }
.error-message, .feedback { margin: -5px 0 0; padding: 12px 14px; border-left: 4px solid var(--danger); background: #f8e5df; color: var(--danger); font-size: 12px; font-weight: 800; }
.security-note { display: flex; align-items: center; gap: 12px; margin-top: 34px; padding-top: 22px; border-top: 1px solid var(--line); color: var(--ink-soft); }
.security-note > span { color: var(--amber); font-size: 12px; }
.security-note p { margin: 0; font-size: 11px; line-height: 1.55; }
.security-note small { color: var(--text-muted); }
.version-line { position: absolute; bottom: 26px; color: #9a9e97; font-size: 9px; letter-spacing: .16em; }
@keyframes login-rise { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: none; } }
@media (max-width: 900px) {
  .login-page { grid-template-columns: 1fr; }
  .brand-panel { min-height: 320px; padding: 30px; }
  .brand-copy { padding: 60px 0 40px; }
  .brand-copy h2 { font-size: 44px; }
  .brand-copy > p:last-child, .brand-panel footer span:last-child { display: none; }
  .login-panel { min-height: 680px; padding-block: 86px; }
}
@media (max-width: 520px) {
  .brand-panel { min-height: 250px; }
  .brand-copy { padding-bottom: 20px; }
  .brand-copy h2 { font-size: 34px; }
  .login-panel { min-height: 620px; padding-inline: 24px; }
  .access-rule { right: 24px; }
}
@media (prefers-reduced-motion: reduce) { .login-card { animation: none; } form button, input { transition: none; } }
</style>
