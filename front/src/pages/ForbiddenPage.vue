<template>
  <main class="state-page">
    <div class="state-mark" aria-hidden="true">403</div>
    <p class="eyebrow">ACCESS BOUNDARY</p>
    <h1>没有访问权限</h1>
    <p>当前身份不具备系统管理权限。若职责发生变化，请联系系统管理员调整固定角色。</p>
    <RouterLink to="/system">返回工作台</RouterLink>
  </main>
</template>

<style scoped>
.state-page {
  width: min(680px, calc(100% - 40px));
  margin: 12vh auto;
  padding: 56px;
  border: 1px solid var(--line-strong);
  background: var(--paper);
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
}

.state-mark {
  position: absolute;
  right: -12px;
  top: -36px;
  font: 800 132px/1 var(--font-display);
  color: rgba(24, 58, 49, 0.07);
}

.eyebrow { color: var(--amber-dark); letter-spacing: .18em; font-weight: 800; }
h1 { font: 700 clamp(34px, 6vw, 58px)/1.1 var(--font-display); margin: 10px 0 18px; color: var(--ink); }
p { color: var(--text-muted); line-height: 1.8; }
a { display: inline-block; margin-top: 24px; color: var(--forest); font-weight: 800; }
</style>
