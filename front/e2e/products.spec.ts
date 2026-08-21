import { expect, test } from '@playwright/test'

test('管理员可创建产品、首个版本和第二个版本', async ({ page }) => {
  const products: any[] = []
  const versions: Record<number, any[]> = {}
  const users = [
    { id: 3, login_name: 'owner', display_name: '负责人', roles: ['product_owner'], status: 'active', last_login_at: null, row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' },
    { id: 4, login_name: 'reviewer', display_name: '审核人', roles: ['reviewer'], status: 'active', last_login_at: null, row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' },
  ]
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] } }))
  await page.route('**/api/v1/users**', route => {
    const role = new URL(route.request().url()).searchParams.get('role')
    const items = users.filter(user => !role || user.roles.includes(role))
    return route.fulfill({ status: 200, json: { items, total: items.length, page: 1, page_size: 20 } })
  })
  await page.route('**/api/v1/products**', async route => {
    const request = route.request(); const url = new URL(request.url()); const method = request.method()
    const versionMatch = url.pathname.match(/products\/(\d+)\/versions(?:\/(\d+))?$/)
    if (versionMatch) {
      const productId = Number(versionMatch[1]); versions[productId] ??= []
      if (method === 'POST') { const body = request.postDataJSON(); const created = { id: versions[productId].length + 1, product_id: productId, ...body, description: body.description ?? null, primary_cvss_version: '3.1', status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }; versions[productId].push(created); return route.fulfill({ status: 201, json: created }) }
      return route.fulfill({ status: 200, json: versions[productId] })
    }
    if (method === 'POST') { const body = request.postDataJSON(); const created = { id: products.length + 1, ...body, status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }; products.push(created); return route.fulfill({ status: 201, json: created }) }
    return route.fulfill({ status: 200, json: { items: products, total: products.length, page: 1, page_size: 20 } })
  })
  await page.route('**/api/v1/ots-components**', route => route.fulfill({ status: 200, json: { items: [], total: 0, page: 1, page_size: 100 } }))
  await page.route('**/api/v1/product-versions/*/ots', route => route.fulfill({ status: 200, json: [] }))

  await page.goto('/system/products')
  await expect(page.locator('aside nav')).toContainText('产品管理')
  await page.getByRole('button', { name: '新建产品' }).click()
  await page.getByLabel('产品编号').fill('P-001')
  await page.getByLabel('产品名称').fill('测试产品')
  await page.getByRole('button', { name: '下一步' }).click()
  await page.getByLabel('版本号').fill('1.0')
  await page.getByLabel('负责人').selectOption('3')
  await page.getByLabel('审核人').selectOption('4')
  await page.getByRole('button', { name: '保存并进入 OTS 清单' }).click()
  await expect(page.getByRole('dialog')).toContainText('第 3 步')
  await expect(page.getByRole('button', { name: '下载 CSV 模板' })).toBeVisible()
  await expect(page.getByRole('button', { name: '导出当前清单' })).toBeVisible()
  await page.getByRole('button', { name: '完成建档' }).click()
  await expect(page.getByText('测试产品')).toBeVisible()

  await page.getByRole('button', { name: '维护测试产品版本' }).click()
  await page.getByRole('button', { name: '新建版本' }).click()
  await page.getByLabel('版本号').fill('2.0')
  await page.getByLabel('负责人').selectOption('3')
  await page.getByLabel('审核人').selectOption('4')
  await page.getByRole('button', { name: '保存版本' }).click()
  await expect(page.getByRole('dialog', { name: /版本维护/ })).toContainText('2.0')
})

test('非管理员不能进入产品管理', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] } }))
  await page.goto('/system/products')
  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
  await expect(page.locator('aside nav')).not.toContainText('产品管理')
})
