import { createRouter, createWebHistory } from 'vue-router'

import { restoreAuthentication } from './auth'
import HealthPage from './pages/HealthPage.vue'
import LoginPage from './pages/LoginPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import SystemPage from './pages/SystemPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/system' },
    { path: '/login', component: LoginPage },
    { path: '/health', component: HealthPage },
    { path: '/system', component: SystemPage, meta: { requiresAuthentication: true } },
    { path: '/:pathMatch(.*)*', component: NotFoundPage },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuthentication) {
    return true
  }
  if (await restoreAuthentication()) {
    return true
  }
  return { path: '/login', query: { redirect: to.fullPath } }
})
