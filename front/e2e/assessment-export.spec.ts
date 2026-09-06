import { expect, test } from '@playwright/test'

test('授权用户预检并下载指定产品版本和 OTS 的评估表', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] } }))
  await page.route('**/api/v1/scopes/me', route => route.fulfill({ status: 200, json: { is_global: false, scopes: [], effective_product_ids: [1], effective_version_ids: [2] } }))
  await page.route('**/api/v1/products?*', route => route.fulfill({ status: 200, json: { items: [{ id: 1, product_name: '产品 A', status: 'active' }], total: 1, page: 1, page_size: 100 } }))
  await page.route('**/api/v1/products/1/versions', route => route.fulfill({ status: 200, json: [{ id: 2, product_id: 1, version_no: '1.0', status: 'active' }] }))
  await page.route('**/api/v1/product-versions/2/ots', route => route.fulfill({ status: 200, json: [{ id: 9, ots_component_id: 3, ots_name: 'OpenSSL', ots_version: '3.0', status: 'active' }] }))
  await page.route('**/api/v1/assessment-exports/preview?*', route => route.fulfill({ status: 200, json: { product_version_id: 2, product_name: '产品 A', version_no: '1.0', ots_id: 3, ots_name: 'OpenSSL', ots_version: '3.0', row_count: 4, previewed_at: '2026-09-06T00:00:00Z' } }))
  await page.route('**/api/v1/assessment-exports/csv?*', route => route.fulfill({ status: 200, headers: { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="assessment_export.csv"' }, body: '\ufeff产品,CVE\r\n产品 A,CVE-2026-0001\r\n' }))

  await page.goto('/system/data-exchange/assessment-export')
  await page.getByLabel('产品版本').selectOption('2')
  await page.locator('[data-field="ots"]').selectOption('3')
  await page.getByRole('button', { name: '预检导出范围' }).click()
  await expect(page.getByText('4 条当前评估')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '确认并下载 CSV' }).click()
  expect((await download).suggestedFilename()).toBe('assessment_export.csv')
  await expect(page.getByText(/导出完成/)).toBeVisible()
})
