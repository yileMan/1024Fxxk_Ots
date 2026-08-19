import { expect, test } from '@playwright/test'

test('用户名密码登录后通过用户 ID Cookie 恢复身份', async ({ page }) => {
  await page.route('**/api/v1/auth/me', async (route) => {
    const cookie = route.request().headers().cookie ?? ''
    await route.fulfill(cookie.includes('ots_user_id=1')
      ? { status: 200, json: { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] } }
      : { status: 401, json: { code: 'AUTH_SESSION_INVALID' } })
  })
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Set-Cookie': 'ots_user_id=1; Path=/' },
      json: { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] },
    })
  })
  await page.goto('/')

  await expect(page).toHaveURL(/\/login\?/)
  expect(new URL(page.url()).searchParams.get('redirect')).toBe('/system')

  await page.getByLabel('登录名').fill('admin')
  await page.getByLabel('密码').fill('password')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/system$/)

  await page.reload()
  await expect(page.getByText('初始管理员')).toBeVisible()
})
