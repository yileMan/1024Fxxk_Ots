import { expect, test } from '@playwright/test'


const validated = {
  id: 12,
  batch_no: 'BATCH-20260822-001',
  format_version: '1.0',
  package_file_name: 'ots_intelligence_20260822_010203.zip',
  package_sha256: 'a'.repeat(64),
  status: 'validated',
  source_name: 'nvd',
  source_release: 'fkie-cad/nvd-json-data-feeds@2026-08-22',
  window_start: '2026-08-21T00:00:00+00:00',
  window_end: '2026-08-22T00:00:00+00:00',
  classification_basis: 'vulnerability_current_facts_v1',
  final_import_diff: false,
  can_import: true,
  internal_matching_pending: false,
  summary: { total: 1, new: 1, update: 0, duplicate: 0, conflict: 0, error: 0 },
  file_stats: {
    'nvd_cves.csv': {
      total: 1, new: 1, update: 0, duplicate: 0, conflict: 0, error: 0,
      samples: [{
        cve_id: 'CVE-2026-0001', vuln_status: 'Analyzed', description: '测试漏洞',
        affected_software_json: [{ vendor: 'openssl', product: 'openssl', version: '3.0.0' }],
        cvss31_score: 7.5, cvss31_severity: 'HIGH',
      }],
    },
  },
  errors: [], total_error_count: 0, truncated_error_count: 0, duplicate: false,
}

const succeeded = {
  ...validated,
  status: 'succeeded',
  final_import_diff: true,
  can_import: false,
  internal_matching_pending: true,
}

const matching = {
  schema_version: '1.0', status: 'pending', matching_rule_version: 'exact-identity-v1',
  version_rule_version: 'natural-version-v1', processed_vulnerability_count: 4,
  candidate_inserted_count: 2, candidate_updated_count: 0, candidate_removed_count: 0,
  candidate_unchanged_count: 0, unmatched_vulnerability_count: 2,
  unmatched_reason_counts: { VERSION_OUTSIDE_RANGE: 1, NO_AFFECTED_RANGE: 1 },
  unmatched_samples: [{ vulnerability_id: 8, cve_id: 'CVE-2026-0803', reason: 'VERSION_OUTSIDE_RANGE' }],
  truncated_unmatched_count: 0,
  candidate_samples: [
    { vulnerability_id: 7, cve_id: 'CVE-2026-0801', ots_component_id: 3, ots_name: 'OpenSSL', ots_version: '1.0', match_method: 'cpe', match_basis: 'OpenSSL 1.0 命中来源受影响版本范围', match_confidence: null, match_evidence: {} },
    { vulnerability_id: 9, cve_id: 'CVE-2026-0802', ots_component_id: 4, ots_name: 'Linux', ots_version: '3.1', match_method: 'cpe', match_basis: 'Linux 3.1 命中来源受影响版本范围', match_confidence: null, match_evidence: {} },
  ],
  truncated_candidate_count: 0, candidate_disclaimer: '候选不等于产品受影响', error_code: null, finished_at: null,
  task_generation: {
    schema_version: '1.0', status: 'pending', task_inserted_count: 2,
    task_reassess_count: 0, task_updated_count: 0, task_unchanged_count: 0,
    task_skipped_count: 0, task_failed_count: 0, skip_reason_counts: {},
    task_samples: [
      { vulnerability_id: 7, cve_id: 'CVE-2026-0801', product_id: 20, product_name: '边界网关', product_version_id: 21, version_no: '1.0', product_ots_id: 22, owner_id: 5, action: 'inserted', reason: null },
      { vulnerability_id: 9, cve_id: 'CVE-2026-0802', product_id: 30, product_name: '终端平台', product_version_id: 31, version_no: '3.1', product_ots_id: 32, owner_id: 6, action: 'inserted', reason: null },
    ],
    truncated_task_count: 0, error_code: null,
  },
}

const failed = {
  ...validated,
  id: 13,
  status: 'failed',
  can_import: false,
  summary: { total: 1, new: 0, update: 0, duplicate: 0, conflict: 0, error: 1 },
  file_stats: { 'nvd_cves.csv': { total: 1, new: 0, update: 0, duplicate: 0, conflict: 0, error: 1, samples: [] } },
  errors: [{
    error_code: 'PACKAGE_CSV_INVALID', file_name: 'nvd_cves.csv', row_number: 2,
    field: 'cvss_json', reason: '字段必须是标准 JSON 数组', rejected_value: '{',
  }],
  total_error_count: 1,
}

async function mockAdmin(page) {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] },
  }))
  await page.route('**/api/v1/scopes/me', route => route.fulfill({
    status: 200,
    json: { user_id: 1, is_admin: true, effective_product_ids: [], effective_product_version_ids: [] },
  }))
}

async function selectPackage(page, body = 'package') {
  await page.locator('input[type="file"]').setInputFiles({
    name: 'ots_intelligence_20260822_010203.zip',
    mimeType: 'application/zip',
    buffer: Buffer.from(body),
  })
  await page.getByRole('button', { name: '上传并开始校验' }).click()
}

test('管理员完成两文件上传、预览、二次确认和成功结果', async ({ page }) => {
  await mockAdmin(page)
  let previewCount = 0
  let executionCount = 0
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({ status: 201, json: validated }))
  await page.route('**/api/v1/import-packages/12/confirm', route => route.fulfill({ status: 200, json: succeeded }))
  await page.route('**/api/v1/import-packages/12/ots-match-preview', route => {
    previewCount += 1
    const repeated = previewCount > 1
    return route.fulfill({
      status: 200,
      json: {
        ...matching,
        task_generation: {
          ...matching.task_generation,
          task_inserted_count: repeated ? 0 : 2,
          task_unchanged_count: repeated ? 2 : 0,
          task_samples: repeated ? matching.task_generation.task_samples.map(task => ({ ...task, action: 'unchanged' })) : matching.task_generation.task_samples,
        },
      },
    })
  })
  await page.route('**/api/v1/import-packages/12/ots-matches', route => {
    executionCount += 1
    const repeated = executionCount > 1
    return route.fulfill({
      status: 200,
      json: {
        ...matching,
        status: 'succeeded',
        task_generation: {
          ...matching.task_generation,
          status: 'succeeded',
          task_inserted_count: repeated ? 0 : 2,
          task_unchanged_count: repeated ? 2 : 0,
          task_samples: repeated ? matching.task_generation.task_samples.map(task => ({ ...task, action: 'unchanged' })) : matching.task_generation.task_samples,
        },
        finished_at: '2026-08-31T08:01:00Z',
      },
    })
  })
  page.on('dialog', dialog => dialog.accept())

  await page.goto('/system/data-exchange/import-packages')
  await expect(page.getByText('固定两文件根目录')).toBeVisible()
  await selectPackage(page)
  await expect(page.getByRole('heading', { name: '校验通过，可以导入漏洞事实' })).toBeVisible()
  await expect(page.getByText('openssl 3.0.0')).toBeVisible()
  await page.getByRole('button', { name: '确认导入漏洞事实' }).click()
  await expect(page.getByRole('heading', { name: '漏洞事实已成功导入' }).first()).toBeVisible()
  await expect(page.getByText('内部 OTS 匹配尚未执行')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认导入漏洞事实' })).toHaveCount(0)
  await page.getByRole('button', { name: '预览内部匹配' }).click()
  await expect(page.getByRole('heading', { name: 'OpenSSL 1.0', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Linux 3.1', exact: true })).toBeVisible()
  await expect(page.getByText('VERSION_OUTSIDE_RANGE')).toBeVisible()
  await expect(page.getByText('候选不等于产品受影响').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: '产品评估任务' })).toBeVisible()
  await expect(page.getByText('边界网关 1.0')).toBeVisible()
  await expect(page.getByText('终端平台 3.1')).toBeVisible()
  await page.getByRole('button', { name: '执行内部匹配与任务生成' }).click()
  await expect(page.getByRole('heading', { name: '内部匹配已完成' })).toBeVisible()
  await expect(page.getByText('任务已生成')).toBeVisible()

  await page.getByRole('button', { name: '预览内部匹配' }).click()
  await expect(page.getByText('新任务').locator('..').getByText('0', { exact: true })).toBeVisible()
  await expect(page.getByText('未变化').locator('..').getByText('2', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '执行内部匹配与任务生成' }).click()
  await expect(page.getByText('新任务').locator('..').getByText('0', { exact: true })).toBeVisible()
  await expect(page.getByText('未变化').locator('..').getByText('2', { exact: true })).toBeVisible()
})

test('字段错误或旧三文件包展示稳定拒绝证据', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({ status: 201, json: failed }))
  await page.route('**/api/v1/import-packages/13/errors', route => route.fulfill({
    status: 200,
    headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="package_validation_errors.csv"' },
    body: 'error_code,file_name,row_number,field,reason,rejected_value\r\n',
  }))
  await page.goto('/system/data-exchange/import-packages')
  await selectPackage(page, 'legacy-three-file-or-invalid-json')
  await expect(page.getByRole('heading', { name: '校验未通过' })).toBeVisible()
  await expect(page.getByText('cvss_json')).toBeVisible()
  await expect(page.getByRole('button', { name: '确认导入漏洞事实' })).toHaveCount(0)
})

test('批次冲突不会回放旧预览', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({
    status: 409,
    json: { code: 'PACKAGE_BATCH_CONFLICT', message: '相同批次号对应不同数据包' },
  }))
  await page.goto('/system/data-exchange/import-packages')
  await selectPackage(page, 'changed-package')
  await expect(page.getByRole('alert')).toContainText('上传或校验失败')
  await expect(page.getByText('BATCH-20260822-001')).toHaveCount(0)
})

test('确认事务失败保留预览并提示重新处理', async ({ page }) => {
  await mockAdmin(page)
  await page.route('**/api/v1/import-packages/validate', route => route.fulfill({ status: 201, json: validated }))
  await page.route('**/api/v1/import-packages/12/confirm', route => route.fulfill({ status: 500, json: { code: 'INTERNAL_ERROR' } }))
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/system/data-exchange/import-packages')
  await selectPackage(page)
  await page.getByRole('button', { name: '确认导入漏洞事实' }).click()
  await expect(page.getByRole('alert')).toContainText('确认导入失败')
  await expect(page.getByText('CVE-2026-0001')).toBeVisible()
})

test('非管理员无法看到入口或直接访问向导', async ({ page }) => {
  await page.route('**/api/v1/auth/me', route => route.fulfill({
    status: 200,
    json: { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] },
  }))
  await page.route('**/api/v1/scopes/me', route => route.fulfill({
    status: 200,
    json: { user_id: 2, is_admin: false, effective_product_ids: [], effective_product_version_ids: [] },
  }))
  await page.goto('/system/data-exchange/import-packages')
  await expect(page.getByRole('heading', { name: '没有访问权限' })).toBeVisible()
  await expect(page.getByRole('link', { name: '数据包导入' })).toHaveCount(0)
})
