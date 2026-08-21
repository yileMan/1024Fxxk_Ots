import { expect, test } from '@playwright/test'

test('管理员可从一级菜单和工作台进入 OTS 主数据', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] } }))
  await page.route('**/api/v1/ots-components**', route => route.fulfill({ status: 200, json: { items: [], total: 0, page: 1, page_size: 20 } }))
  await page.goto('/system')
  await expect(page.getByRole('link', { name: 'OTS', exact: true })).toBeVisible()
  await expect(page.locator('.module-card h2', { hasText: 'OTS 主数据' })).toBeVisible()
  await page.getByRole('link', { name: 'OTS', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'OTS 主数据' })).toBeVisible()
})

test('非管理员不能进入 OTS 管理', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] } }))
  await page.goto('/system/ots')
  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'OTS', exact: true })).toHaveCount(0)
})
