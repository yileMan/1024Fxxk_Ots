import { expect, test } from '@playwright/test'

test('管理员可以进入用户管理并创建多角色用户', async ({ page }) => {
  const users = [
    {
      id: 2,
      login_name: 'zhangsan',
      display_name: '张三',
      roles: ['reviewer'],
      status: 'active',
      last_login_at: null,
      row_version: 1,
      created_at: '2026-08-19T12:00:00',
      updated_at: '2026-08-19T12:00:00',
    },
  ]
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] },
  }))
  await page.route('**/api/v1/users**', async (route) => {
    if (route.request().method() === 'POST') {
      const payload = route.request().postDataJSON()
      const created = {
        id: 3,
        login_name: payload.login_name,
        display_name: payload.display_name,
        roles: payload.roles,
        status: 'active',
        last_login_at: null,
        row_version: 1,
        created_at: '2026-08-19T12:00:00',
        updated_at: '2026-08-19T12:00:00',
      }
      users.push(created)
      await route.fulfill({ status: 201, json: created })
      return
    }
    await route.fulfill({ status: 200, json: { items: users, total: users.length, page: 1, page_size: 20 } })
  })

  await page.goto('/system/users')
  await expect(page.getByRole('heading', { name: '用户与角色' })).toBeVisible()
  await page.getByRole('button', { name: '新建用户' }).click()
  await page.getByLabel('登录名').fill('new-owner')
  await page.getByLabel('显示名称').fill('新负责人')
  await page.getByLabel('初始密码').fill('secret')
  await page.getByRole('checkbox', { name: /产品负责人/ }).check()
  await page.getByRole('checkbox', { name: /审核人/ }).check()
  await page.getByRole('button', { name: '创建用户' }).click()

  await expect(page.getByText('新负责人')).toBeVisible()
  await expect(page.getByRole('table').getByText('产品负责人')).toBeVisible()
})

test('非管理员直接进入用户管理会得到明确拒绝', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] },
  }))
  await page.goto('/system/users')

  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
})
