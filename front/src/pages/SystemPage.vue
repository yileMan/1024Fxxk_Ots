<template>
  <main class="system-page">
    <p class="eyebrow">CONTROL DESK / OVERVIEW</p>
    <h1>系统工作台</h1>
    <p class="intro">这里是 OTS 信息维护平台的内网入口。维护产品、版本和实际使用的 OTS 清单，为后续采集与评估建立可信主数据。</p>
    <div class="module-grid">
      <RouterLink v-if="isAdmin" class="module-card featured" to="/system/products">
        <span>01</span><small>主数据</small><h2>产品管理</h2><p>维护产品、版本、负责人、审核人和版本 OTS 清单。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="hasScopedProducts" class="module-card featured" to="/system/my-products">
        <span>01</span><small>授权范围</small><h2>我的产品</h2><p>只读查看已授权产品、版本和对应 OTS 清单。</p><b>查看产品 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card" to="/system/ots">
        <span>02</span><small>共享组件</small><h2>OTS 主数据</h2><p>维护 OTS 名称、版本、官方网站、EOL 与关联产品。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card" to="/system/users">
        <span>03</span><small>系统管理</small><h2>用户与角色</h2><p>维护账号、固定角色、密码与人员状态。</p><b>进入模块 ↗</b>
      </RouterLink>
      <RouterLink v-if="isAdmin" class="module-card exchange" to="/system/data-exchange/collector-scope">
        <span>04</span><small>离线数据交换</small><h2>采集范围</h2><p>预览实际在用 OTS、覆盖位置和范围变化，下载规范 CSV。</p><b>生成范围 ↗</b>
      </RouterLink>
      <RouterLink class="module-card" to="/health">
        <span>05</span><small>平台运行</small><h2>服务状态</h2><p>检查 API 与数据库可用性。</p><b>查看状态 ↗</b>
      </RouterLink>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { authentication } from '../auth'

const isAdmin = computed(() => authentication.user?.roles.includes('admin') ?? false)
const hasScopedProducts = computed(() => !isAdmin.value && (authentication.scope?.effective_product_ids.length ?? 0) > 0)
</script>

<style scoped>
.system-page { max-width: 1180px; margin: 0 auto; padding: 72px 32px; }
.eyebrow { color: var(--amber-dark); font-size: 11px; font-weight: 900; letter-spacing: .2em; }
h1 { margin: 12px 0; color: var(--ink); font: 700 clamp(46px, 7vw, 76px)/1 var(--font-display); letter-spacing: -.04em; }
.intro { max-width: 600px; color: var(--text-muted); line-height: 1.8; }
.module-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-top: 50px; }
.module-card { min-height: 280px; padding: 30px; border: 1px solid var(--line-strong); background: var(--paper); color: var(--ink); text-decoration: none; box-shadow: var(--shadow-card); transition: transform .2s; }
.module-card:hover { transform: translateY(-4px); }
.module-card.featured { color: var(--paper); background: var(--forest); }
.module-card.exchange { border-top: 4px solid var(--brand-red); }
.module-card > span { float: right; color: var(--amber); font: 700 44px var(--font-display); }
.module-card small { color: var(--amber-dark); font-weight: 900; letter-spacing: .15em; }
.featured small { color: var(--amber); }
.featured > span, .featured small, .featured b { color: #fff; opacity: .82; }
.module-card h2 { margin: 44px 0 12px; font: 700 32px var(--font-display); }
.module-card p { max-width: 330px; line-height: 1.7; opacity: .72; }
.module-card b { display: inline-block; margin-top: 28px; color: var(--amber); font-size: 12px; }
@media (max-width: 650px) { .module-grid { grid-template-columns: 1fr; } }
</style>
