import { expect, test } from '@playwright/test'

test('用户名密码登录后通过用户 ID Cookie 恢复身份', async ({ page }) => {
  await page.route('**/api/v1/auth/me', async (route) => {
    const cookie = route.request().headers().cookie ?? ''
    await route.fulfill(
      cookie.includes('ots_user_id=1')
        ? { status: 200, json: { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] } }
        : cookie.includes('ots_user_id=2')
          ? { status: 200, json: { id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] } }
          : { status: 401, json: { code: 'AUTH_SESSION_INVALID' } },
    )
  })
  await page.route('**/api/v1/auth/login', async (route) => {
    const payload = route.request().postDataJSON()
    const isOwner = payload.login_name === 'owner'
    await route.fulfill({
      status: 200,
      headers: { 'Set-Cookie': `ots_user_id=${isOwner ? 2 : 1}; Path=/` },
      json: isOwner
        ? { id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] }
        : { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] },
    })
  })
  await page.route('**/api/v1/auth/logout', async (route) => {
    await route.fulfill({ status: 204, headers: { 'Set-Cookie': 'ots_user_id=; Max-Age=0; Path=/' } })
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

  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('登录名').fill('owner')
  await page.getByLabel('密码').fill('owner-password')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/system$/)
  await expect(page.locator('.identity-chip strong')).toHaveText('产品负责人')
})
