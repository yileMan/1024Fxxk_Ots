import { expect, test, type Page } from '@playwright/test'

const auth = async (page: Page) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] } }))
}

test('管理员筛选变更记录并安全查看差异', async ({ page }) => {
  await auth(page)
  await page.route('**/api/v1/audit-logs?*', route => route.fulfill({ status: 200, json: { items: [{ id: 8, user_id: 1, actor_display_name: '管理员', action: 'update', object_type: 'product', object_id: '2', detail_keys: ['changes'], created_at: '2026-09-06T02:00:00Z' }], total: 1, next_cursor: null, limit: 20 } }))
  await page.route('**/api/v1/audit-logs/8', route => route.fulfill({ status: 200, json: { id: 8, user_id: 1, actor_display_name: '管理员', action: 'update', object_type: 'product', object_id: '2', detail: { changes: { product_name: { from: '旧', to: '<script>alert(1)</script>' } } }, created_at: '2026-09-06T02:00:00Z' } }))
  await page.goto('/system/audit-logs')
  await expect(page.getByRole('heading', { name: '变更记录' })).toBeVisible()
  await page.getByRole('button', { name: '查看变更记录 8' }).click()
  await expect(page.getByText('<script>alert(1)</script>', { exact: false })).toBeVisible()
  await expect(page.locator('[role="dialog"] script')).toHaveCount(0)
})

test('运行状态显示局部故障并可刷新恢复', async ({ page }) => {
  await auth(page)
  const component = (status: string, summary: string) => ({ status, observed_at: '2026-09-06T02:00:00Z', summary })
  let failed = true
  await page.route('**/api/v1/system/operations', route => {
    const database = failed ? component('error', '数据库状态不可用') : component('ok', '数据库连接正常')
    failed = false
    return route.fulfill({ status: 200, json: { overall_status: database.status, observed_at: '2026-09-06T02:00:00Z', application: { ...component('ok', '应用版本可用'), version: '1.0.0' }, database, disk: component('ok', '磁盘空间充足'), backup: component('unknown', '备份状态未配置'), latest_import: component('unknown', '暂无导入记录'), latest_failure: component('ok', '无失败记录') } })
  })
  await page.goto('/system/operations')
  await expect(page.getByText('数据库状态不可用')).toBeVisible()
  await page.getByRole('button', { name: '刷新状态' }).click()
  await expect(page.getByText('数据库连接正常')).toBeVisible()
})
