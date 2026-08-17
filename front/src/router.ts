import { createRouter, createWebHistory } from 'vue-router'

import { authentication, restoreAuthentication } from './auth'
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
  const user = await restoreAuthentication()
  if (to.meta.requiresAuthentication && !user) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && user) {
    const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/system'
    return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/system'
  }
  return true
})

export function isAuthenticated(): boolean {
  return authentication.user !== null
}
