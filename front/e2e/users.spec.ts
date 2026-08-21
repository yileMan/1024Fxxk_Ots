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
  let conflictOnce = true
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] },
  }))
  await page.route('**/api/v1/users**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const userIdMatch = url.pathname.match(/\/users\/(\d+)/)
    const target = userIdMatch ? users.find((user) => user.id === Number(userIdMatch[1])) : undefined
    if (method === 'POST' && url.pathname.endsWith('/reset-password') && target) {
      target.row_version += 1
      await route.fulfill({ status: 200, json: target })
      return
    }
    if (method === 'POST' && url.pathname.endsWith('/disable') && target) {
      target.status = 'disabled'
      target.row_version += 1
      await route.fulfill({ status: 200, json: target })
      return
    }
    if (method === 'PUT' && target) {
      if (conflictOnce) {
        conflictOnce = false
        target.row_version += 1
        await route.fulfill({ status: 409, json: { code: 'USER_VERSION_CONFLICT' } })
        return
      }
      const payload = request.postDataJSON()
      target.display_name = payload.display_name
      target.roles = payload.roles
      target.row_version += 1
      await route.fulfill({ status: 200, json: target })
      return
    }
    if (method === 'GET' && target) {
      await route.fulfill({ status: 200, json: target })
      return
    }
    if (method === 'POST') {
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
  const navigationItems = await page.locator('aside.app-sidebar nav a').allTextContents()
  expect(navigationItems.map((item) => item.trim())).toEqual(['工作台', '产品管理', 'OTS', '用户与角色', '运行状态'])
  const layout = await page.evaluate(() => {
    const sidebar = document.querySelector('aside.app-sidebar')?.getBoundingClientRect()
    const content = document.querySelector('main')?.getBoundingClientRect()
    return {
      sidebarX: sidebar?.x,
      sidebarWidth: sidebar?.width,
      contentX: content?.x,
      brandRed: getComputedStyle(document.documentElement).getPropertyValue('--brand-red').trim(),
    }
  })
  expect(layout.sidebarX).toBe(0)
  expect(layout.sidebarWidth).toBeGreaterThanOrEqual(220)
  expect(layout.contentX).toBeGreaterThanOrEqual(220)
  expect(layout.brandRed.toLowerCase()).toBe('#d71920')
  await page.getByRole('button', { name: '新建用户' }).click()
  await page.getByLabel('登录名').fill('new-owner')
  await page.getByLabel('显示名称').fill('新负责人')
  await page.getByLabel('初始密码').fill('secret')
  await page.getByRole('checkbox', { name: /产品负责人/ }).check()
  await page.getByRole('checkbox', { name: /审核人/ }).check()
  await page.getByRole('button', { name: '创建用户' }).click()

  await expect(page.getByText('新负责人')).toBeVisible()
  await expect(page.getByRole('table').getByText('产品负责人')).toBeVisible()

  await page.getByRole('button', { name: '编辑新负责人' }).click()
  await page.getByLabel('显示名称').fill('新负责人（已编辑）')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByText('数据已被其他管理员更新')).toBeVisible()
  await expect(page.getByLabel('显示名称')).toHaveValue('新负责人（已编辑）')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(page.getByText('新负责人（已编辑）')).toBeVisible()

  await page.getByRole('button', { name: '重置新负责人（已编辑）密码' }).click()
  await page.getByLabel('新密码').fill('new-secret')
  await page.getByRole('button', { name: '确认重置' }).click()

  await page.getByRole('button', { name: '停用新负责人（已编辑）' }).click()
  await expect(page.getByRole('dialog')).toContainText('保留全部历史记录')
  await page.getByRole('button', { name: '确认停用' }).click()
  await expect(page.getByRole('table').getByText('已停用')).toBeVisible()
})

test('非管理员直接进入用户管理会得到明确拒绝', async ({ page }) => {
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({
    status: 200,
    json: { id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] },
  }))
  await page.goto('/system/users')

  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
})
