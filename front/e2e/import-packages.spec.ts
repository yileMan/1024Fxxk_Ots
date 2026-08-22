import { expect, test } from '@playwright/test'


const validated = {
  id: 12,
  batch_no: 'BATCH-20260822-001',
  format_version: '1.0',
  package_file_name: 'ots_intelligence_20260822_010203.zip',
  package_sha256: 'a'.repeat(64),
  status: 'validated',
  scope_export_id: '2ef57421-4978-47b2-897c-3b8dfe7e1ea0',
  scope_count: 1,
  classification_basis: 'package_structure_v1',
  final_import_diff: false,
  can_import: false,
  summary: { total: 7, new: 7, update: 0, duplicate: 0, conflict: 0, error: 0 },
  file_stats: {
    'vulnerabilities.csv': {
      total: 1, new: 1, update: 0, duplicate: 0, conflict: 0, error: 0,
      samples: [{ cve_id: 'CVE-2026-0001', status: 'published' }],
    },
  },
  errors: [],
  total_error_count: 0,
  truncated_error_count: 0,
  duplicate: false,
}

const failed = {
  ...validated,
  id: 13,
  status: 'failed',
  summary: { total: 7, new: 5, update: 0, duplicate: 0, conflict: 0, error: 2 },
  errors: [{
    error_code: 'PACKAGE_SCOPE_INVALID', file_name: 'matches.csv', row_number: 2,
    field: 'ots_id', reason: '候选匹配引用范围外 OTS', rejected_value: '999',
  }],
  total_error_count: 2,
  truncated_error_count: 1,
}

async function mockAdmin(page) {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] },
  }))
}

test('管理员上传合规包并查看只读校验预览', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({ status: 201, json: validated }))

  await page.goto('/system')
  await page.getByRole('link', { name: '数据包导入', exact: true }).click()
  await expect(page.getByRole('heading', { name: '数据包导入' })).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles({
    name: 'ots_intelligence_20260822_010203.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from('package'),
  })
  await page.getByRole('button', { name: '上传并开始校验' }).click()
  await expect(page.getByRole('heading', { name: '校验通过，尚未正式写入' })).toBeVisible()
  await expect(page.getByText('BATCH-20260822-001')).toBeVisible()
  await expect(page.getByText('CVE-2026-0001')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认导入尚未开放' })).toBeDisabled()
})

test('损坏包展示精确错误并下载有界清单', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({ status: 201, json: failed }))
  await page.route('**/api/v1/import-packages/13/errors', route => route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="package_validation_errors.csv"' },
    body: 'error_code,file_name,row_number,field,reason,rejected_value\r\n',
  }))
  await page.goto('/system/data-exchange/import-packages')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'ots_intelligence_20260822_010203.zip', mimeType: 'application/zip', buffer: Buffer.from('bad-package'),
  })
  await page.getByRole('button', { name: '上传并开始校验' }).click()
  await expect(page.getByRole('heading', { name: '校验未通过' })).toBeVisible()
  await expect(page.getByText('matches.csv')).toBeVisible()
  await expect(page.getByText('第 2 行')).toBeVisible()
  await page.getByRole('button', { name: '下载错误清单 CSV' }).click()
  await expect(page.getByText('已下载 package_validation_errors.csv')).toBeVisible()
})

test('非管理员无法看到入口或直接访问向导', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] },
  }))
  await page.goto('/system/data-exchange/import-packages')
  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
  await expect(page.getByRole('link', { name: '数据包导入' })).toHaveCount(0)
})
