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
  cvss_metrics: Record<string, string> | null
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
    submitted_by: null as number | null,
    submitted_at: null as string | null,
    review_decision: null as string | null,
    review_comment: null as string | null,
    reviewer_id: null as number | null,
    reviewed_at: null as string | null,
    actions: { can_submit: editable, can_approve: false, can_return: false, unavailable_reason: null as string | null },
    return_reason: null as string | null,
    reassess_reason: null as string | null,
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
      cvss31_vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
      cvss31_source: 'nvd@nist.gov',
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
      cvss_metrics: null,
    } as Draft,
    environmental_scoring: {
      available: true,
      unavailable_reason: null,
      metrics: null,
      score: null,
      vector: null,
      calculator_version: null,
    },
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
    if (payload.cvss_metrics) {
      detail.environmental_scoring = {
        available: true, unavailable_reason: null, metrics: payload.cvss_metrics,
        score: 9.8, vector: 'CVSS:3.1/server-authoritative-vector', calculator_version: 'ots-cvss31-1',
      }
    }
    detail.row_version += 1
    await route.fulfill({ status: 200, json: detail })
  })

  await page.goto('/system/assessments/tasks?queue=pending&page=1')
  await page.getByRole('link', { name: /填写评估/ }).click()
  await page.getByLabel('分析摘要').fill('部分草稿分析')
  await page.getByLabel(/机密性要求/).selectOption('H')
  await expect(page.getByText('未保存预览')).toBeVisible()
  await page.getByRole('button', { name: '保存草稿' }).click()
  await expect(page.getByText('草稿已保存')).toBeVisible()
  await expect(page.getByText('CVSS:3.1/server-authoritative-vector')).toBeVisible()

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

test('负责人确认提交后采用服务端待审核只读状态', async ({ page }) => {
  await authenticate(page)
  const server = assessmentDetail()
  await page.route('**/api/v1/assessments/9**', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, json: server })
    if (route.request().url().endsWith('/submit')) {
      server.status = 'submitted'
      server.editable = false
      server.row_version = 2
      server.submitted_by = 2
      server.submitted_at = '2026-09-03T10:00:00Z'
      server.actions = { can_submit: false, can_approve: false, can_return: false, unavailable_reason: 'ASSESSMENT_ALREADY_SUBMITTED' }
      return route.fulfill({ status: 200, json: server })
    }
    return route.fulfill({ status: 500 })
  })

  await page.goto('/system/assessments/9?from=pending')
  await page.getByRole('button', { name: '提交审核' }).click()
  await expect(page.getByRole('dialog')).toContainText('提交后当前修订将冻结')
  await page.getByRole('button', { name: '确认提交' }).click()
  await expect(page.getByText('评估已提交审核')).toBeVisible()
  await expect(page.getByText('REV 1 · 待审核')).toBeVisible()
  await expect(page.getByLabel('分析摘要')).toBeDisabled()
})

test('审核人可退回且空意见不能发送请求', async ({ page }) => {
  await authenticate(page, reviewer)
  const server = assessmentDetail(false)
  server.status = 'submitted'
  server.submitted_by = 2
  server.submitted_at = '2026-09-03T10:00:00Z'
  server.actions = { can_submit: false, can_approve: true, can_return: true, unavailable_reason: null }
  let returnRequests = 0
  await page.route('**/api/v1/assessments/9**', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, json: server })
    if (route.request().url().endsWith('/return')) {
      returnRequests += 1
      const payload = route.request().postDataJSON() as { review_comment: string }
      server.status = 'returned'
      server.row_version = 2
      server.review_decision = 'returned'
      server.review_comment = payload.review_comment.trim()
      server.return_reason = server.review_comment
      server.reviewer_id = 3
      server.reviewed_at = '2026-09-03T10:10:00Z'
      server.actions = { can_submit: false, can_approve: false, can_return: false, unavailable_reason: 'RETURNED_REVISION_READ_ONLY' }
      return route.fulfill({ status: 200, json: server })
    }
    return route.fulfill({ status: 500 })
  })

  await page.goto('/system/assessments/9?from=submitted')
  await page.getByRole('button', { name: '退回修改' }).click()
  await page.getByRole('button', { name: '确认退回' }).click()
  await expect(page.locator('[data-error-for="review_comment"]')).toContainText('必须填写')
  expect(returnRequests).toBe(0)
  await page.getByLabel('退回意见').fill('  请补充影响依据  ')
  await page.getByRole('button', { name: '确认退回' }).click()
  await expect(page.getByText('评估已退回')).toBeVisible()
  await expect(page.getByText(/等待创建新修订/)).toBeVisible()
  expect(returnRequests).toBe(1)
})

test('审核人确认通过后直接完成评估', async ({ page }) => {
  await authenticate(page, reviewer)
  const server = assessmentDetail(false)
  server.status = 'submitted'
  server.submitted_by = 2
  server.submitted_at = '2026-09-03T10:00:00Z'
  server.actions = { can_submit: false, can_approve: true, can_return: true, unavailable_reason: null }
  await page.route('**/api/v1/assessments/9**', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, json: server })
    if (route.request().url().endsWith('/approve')) {
      server.status = 'completed'
      server.row_version = 2
      server.review_decision = 'approved'
      server.reviewer_id = 3
      server.reviewed_at = '2026-09-03T10:10:00Z'
      server.actions = { can_submit: false, can_approve: false, can_return: false, unavailable_reason: 'ASSESSMENT_COMPLETED' }
      return route.fulfill({ status: 200, json: server })
    }
    return route.fulfill({ status: 500 })
  })

  await page.goto('/system/assessments/9?from=submitted')
  await page.getByRole('button', { name: '审核通过' }).click()
  await expect(page.getByRole('dialog')).toContainText('直接进入已完成')
  await page.getByRole('button', { name: '确认通过' }).click()
  await expect(page.getByText('评估已审核通过')).toBeVisible()
  await expect(page.getByText('REV 1 · 已完成')).toBeVisible()
})

test('自审分配提示重新指定且直接越权审核被服务端拒绝', async ({ page }) => {
  await authenticate(page)
  const server = assessmentDetail()
  await page.route('**/api/v1/assessments/9**', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 200, json: server })
    if (route.request().url().endsWith('/submit')) {
      return route.fulfill({ status: 409, json: { code: 'REVIEWER_REASSIGNMENT_REQUIRED', message: '提交人与当前审核人相同，请先重新分配审核人' } })
    }
    if (route.request().url().endsWith('/approve')) {
      return route.fulfill({ status: 403, json: { code: 'ASSESSMENT_FORBIDDEN', message: '无权审核该产品评估' } })
    }
    return route.fulfill({ status: 500 })
  })

  await page.goto('/system/assessments/9?from=pending')
  await page.getByRole('button', { name: '提交审核' }).click()
  await page.getByRole('button', { name: '确认提交' }).click()
  await expect(page.getByRole('alert')).toContainText('请先重新分配审核人')

  const status = await page.evaluate(async () => (await fetch('/api/v1/assessments/9/approve', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ row_version: 1 }),
  })).status)
  expect(status).toBe(403)
})
