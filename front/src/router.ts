import { createRouter, createWebHistory } from 'vue-router'

import { restoreAuthentication } from './auth'
import HealthPage from './pages/HealthPage.vue'
import ForbiddenPage from './pages/ForbiddenPage.vue'
import LoginPage from './pages/LoginPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import SystemPage from './pages/SystemPage.vue'
import UserAdminPage from './pages/UserAdminPage.vue'
import ProductAdminPage from './pages/ProductAdminPage.vue'
import OtsAdminPage from './pages/OtsAdminPage.vue'
import MyProductsPage from './pages/MyProductsPage.vue'
import CollectorScopePage from './pages/CollectorScopePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/system' },
    { path: '/login', component: LoginPage },
    { path: '/health', component: HealthPage },
    { path: '/system', component: SystemPage, meta: { requiresAuthentication: true } },
    { path: '/system/users', component: UserAdminPage, meta: { requiresAuthentication: true, requiresAdmin: true } },
    { path: '/system/products', component: ProductAdminPage, meta: { requiresAuthentication: true, requiresAdmin: true } },
    { path: '/system/my-products', component: MyProductsPage, meta: { requiresAuthentication: true } },
    { path: '/system/ots', component: OtsAdminPage, meta: { requiresAuthentication: true, requiresAdmin: true } },
    { path: '/system/data-exchange/collector-scope', component: CollectorScopePage, meta: { requiresAuthentication: true, requiresAdmin: true } },
    { path: '/forbidden', component: ForbiddenPage, meta: { requiresAuthentication: true } },
    { path: '/:pathMatch(.*)*', component: NotFoundPage },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuthentication) {
    return true
  }
  const user = await restoreAuthentication()
  if (!user) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.requiresAdmin && !user.roles.includes('admin')) return { path: '/forbidden' }
  return true
})
