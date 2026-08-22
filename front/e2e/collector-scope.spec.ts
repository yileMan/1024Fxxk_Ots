import { expect, test } from '@playwright/test'

const preview = {
  scope_count: 1,
  items: [
    {
      ots_id: 7,
      ots_name: 'OpenSSL',
      ots_version: '3.0',
      official_website: 'https://openssl.org',
      last_covered_time: null,
      is_initial_collection: true,
    },
  ],
  comparison_baseline: { available: false, batch_no: null, finished_at: null },
  changes: { added_ots_ids: [], removed_ots_ids: [], added_count: 0, removed_count: 0 },
}

test('管理员从数据交换入口预览并下载采集范围', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] },
  }))
  await page.route('**/api/v1/collector-scope', route => route.fulfill({ status: 200, json: preview }))
  await page.route('**/api/v1/collector-scope/export', route => route.fulfill({
    status: 200,
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': 'attachment; filename="collector_scope.csv"',
      'X-Scope-Export-ID': '9aa5f26f-7f89-4653-8e2e-9c995e849d63',
      'X-Content-SHA256': 'c'.repeat(64),
    },
    body: 'scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time\r\n',
  }))

  await page.goto('/system')
  await page.getByRole('link', { name: '采集范围' }).click()
  await expect(page.getByRole('heading', { name: '采集范围' })).toBeVisible()
  await expect(page.getByText('OpenSSL')).toBeVisible()
  await expect(page.getByText('首次采集')).toBeVisible()
  await page.getByRole('button', { name: '下载 collector_scope.csv' }).click()
  await expect(page.getByText(/9aa5f26f/)).toBeVisible()
})

test('非管理员无法从导航或直接路由进入采集范围', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] },
  }))
  await page.goto('/system/data-exchange/collector-scope')
  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
  await expect(page.getByRole('link', { name: '采集范围' })).toHaveCount(0)
})
