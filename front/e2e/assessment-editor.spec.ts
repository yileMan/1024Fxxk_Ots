import { expect, test, type Page, type Route } from '@playwright/test'


type Draft = {
  analysis_summary: string | null
  trigger_conditions: string | null
  affected_functions: string | null
  applicability: string
  applicability_basis: string | null
  product_impact: string | null
  existing_controls: string | null
  treatment: string | null
  treatment_detail: string | null
  evidence_text: string | null
}

const owner = { id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] }
const reviewer = { id: 3, login_name: 'reviewer', display_name: '审核人', roles: ['reviewer'] }

function assessmentDetail(editable = true) {
  return {
    assessment_id: 9,
    revision_no: 1,
    is_current: true,
    status: 'pending',
    owner_id: 2,
    row_version: 1,
    editable,
    return_reason: null,
    reassess_reason: null,
    product: { id: 10, name: '监护仪' },
    product_version: { id: 11, version_no: '3.0' },
    ots: { id: 13, name: 'OpenSSL', version: '3.0.0' },
    vulnerability: {
      id: 8,
      cve_id: 'CVE-2026-0900',
      source_status: 'Analyzed',
      description: '来源事实',
      cvss31_score: 8.1,
      cvss31_severity: 'HIGH',
      is_kev: false,
    },
    candidate: null,
    candidate_disclaimer: '候选不等于产品受影响',
    draft: {
      analysis_summary: null,
      trigger_conditions: null,
      affected_functions: null,
      applicability: 'pending',
      applicability_basis: null,
      product_impact: null,
      existing_controls: null,
      treatment: null,
      treatment_detail: null,
      evidence_text: null,
    } as Draft,
  }
}

async function authenticate(page: Page, user = owner): Promise<void> {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 200, json: user }))
  await page.route('**/api/v1/scopes/me', route => route.fulfill({
    status: 200,
    json: { is_global: false, scopes: [], effective_product_ids: [10], effective_version_ids: [11] },
  }))
}

async function fulfillValidation(route: Route, path: string, message: string): Promise<void> {
  await route.fulfill({
    status: 422,
    json: {
      code: 'ASSESSMENT_VALIDATION_ERROR',
      message: '评估草稿校验失败',
      fields: [{ path, message }],
    },
  })
}

test('负责人从待办进入、保存部分草稿并看到条件校验', async ({ page }) => {
  await authenticate(page)
  const detail = assessmentDetail()
  await page.route('**/api/v1/assessments/tasks**', route => route.fulfill({
    status: 200,
    json: {
      items: [{
        assessment_id: 9, vulnerability_id: 8, revision_no: 1, status: 'pending', cve_id: 'CVE-2026-0900',
        product_id: 10, product_name: '监护仪', product_version_id: 11, version_no: '3.0',
        product_ots_id: 12, ots_component_id: 13, ots_name: 'OpenSSL', ots_version: '3.0.0',
        owner_id: 2, reviewer_id: 3, source_severity: 'HIGH', updated_at: '2026-09-01T08:00:00Z',
      }],
      total: 1,
      page: 1,
      page_size: 20,
    },
  }))
  await page.route('**/api/v1/assessments/9**', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, json: detail })
      return
    }
    const payload = route.request().postDataJSON() as Draft & { row_version: number }
    if (payload.applicability !== 'pending' && !payload.applicability_basis?.trim()) {
      await fulfillValidation(route, 'applicability_basis', '选择适用性结论时必须填写依据')
      return
    }
    if (['accept_risk', 'no_action'].includes(payload.treatment ?? '') && !payload.treatment_detail?.trim()) {
      await fulfillValidation(route, 'treatment_detail', '该处置方式必须填写说明')
      return
    }
    detail.draft = { ...payload }
    detail.row_version += 1
    await route.fulfill({ status: 200, json: detail })
  })

  await page.goto('/system/assessments/tasks?queue=pending&page=1')
  await page.getByRole('link', { name: /填写评估/ }).click()
  await page.getByLabel('分析摘要').fill('部分草稿分析')
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page.getByText('草稿已保存')).toBeVisible()

  await page.getByLabel('适用性', { exact: true }).selectOption('not_affected')
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page.locator('[data-error-for="applicability_basis"]')).toContainText('必须填写依据')

  await page.getByLabel('适用性依据').fill('产品未启用相关功能')
  for (const treatment of ['accept_risk', 'no_action']) {
    await page.getByLabel('处置建议', { exact: true }).selectOption(treatment)
    await page.getByRole('button', { name: '保存草稿' }).click()
    await expect(page.locator('[data-error-for="treatment_detail"]')).toContainText('必须填写说明')
  }
})

test('非负责人只能读取评估且没有保存操作', async ({ page }) => {
  await authenticate(page, reviewer)
  await page.route('**/api/v1/assessments/9', route => route.fulfill({ status: 200, json: assessmentDetail(false) }))

  await page.goto('/system/assessments/9?from=submitted')
  await expect(page.getByText('只读', { exact: true })).toBeVisible()
  await expect(page.getByLabel('分析摘要')).toBeDisabled()
  await expect(page.getByRole('button', { name: '保存草稿' })).toHaveCount(0)
})

test('两个客户端使用旧版本保存时不覆盖先成功的草稿', async ({ browser }) => {
  const server = assessmentDetail()
  const setupPage = async (page: Page) => {
    await authenticate(page)
    await page.route('**/api/v1/assessments/9**', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, json: server })
        return
      }
      const payload = route.request().postDataJSON() as Draft & { row_version: number }
      if (payload.row_version !== server.row_version) {
        await route.fulfill({
          status: 409,
          json: { code: 'ASSESSMENT_VERSION_CONFLICT', message: '评估已被其他客户端更新，请刷新后重试' },
        })
        return
      }
      server.draft = { ...payload }
      server.row_version += 1
      await route.fulfill({ status: 200, json: server })
    })
    await page.goto('/system/assessments/9?from=pending')
  }

  const firstContext = await browser.newContext()
  const secondContext = await browser.newContext()
  const first = await firstContext.newPage()
  const second = await secondContext.newPage()
  await Promise.all([setupPage(first), setupPage(second)])

  await second.getByLabel('分析摘要').fill('第二客户端未保存内容')
  await first.getByLabel('分析摘要').fill('第一客户端已保存内容')
  await first.getByRole('button', { name: '保存草稿' }).click()
  await expect(first.getByText('草稿已保存')).toBeVisible()
  await second.getByRole('button', { name: '保存草稿' }).click()

  await expect(second.getByRole('alert')).toContainText('已被其他客户端更新')
  await expect(second.getByLabel('分析摘要')).toHaveValue('第二客户端未保存内容')
  await expect(second.getByRole('button', { name: '刷新服务器数据' })).toBeVisible()
  expect(server.draft.analysis_summary).toBe('第一客户端已保存内容')

  await firstContext.close()
  await secondContext.close()
})
