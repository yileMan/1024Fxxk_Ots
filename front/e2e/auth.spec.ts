import { expect, test } from '@playwright/test'

test('未登录用户看到登录页并可提交账号密码', async ({ page }) => {
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({ status: 401, json: { code: 'AUTH_SESSION_INVALID' } })
  })
  await page.goto('/login')

  await expect(page.getByRole('heading', { name: '登录 OTS 信息维护平台' })).toBeVisible()
  await expect(page.getByLabel('登录名')).toBeVisible()
  await expect(page.getByLabel('密码')).toBeVisible()
})
