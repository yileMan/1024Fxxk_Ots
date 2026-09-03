import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssessmentDetailPage from './AssessmentDetailPage.vue'


const fetchMock = vi.fn()

function detail(overrides: Record<string, unknown> = {}) {
  return {
    assessment_id: 9,
    revision_no: 2,
    parent_revision_id: null,
    current_revision_id: 9,
    is_current: true,
    status: 'pending',
    owner_id: 2,
    row_version: 1,
    editable: true,
    submitted_by: null,
    submitted_at: null,
    review_decision: null,
    review_comment: null,
    reviewer_id: null,
    reviewed_at: null,
    actions: { can_submit: true, can_approve: false, can_return: false, can_create_revision: false, unavailable_reason: null },
    return_reason: '<b>补充影响依据</b>',
    reassess_reason: null,
    reason_type: 'review_return',
    product: { id: 1, name: '监护仪' },
    product_version: { id: 2, version_no: '3.0' },
    ots: { id: 3, name: 'OpenSSL', version: '3.0.0' },
    vulnerability: {
      id: 8,
      cve_id: 'CVE-2026-0900',
      source_status: 'Analyzed',
      description: '<img src=x onerror=alert(1)>',
      cvss31_score: 8.1,
      cvss31_severity: 'HIGH',
      cvss31_vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
      cvss31_source: 'nvd@nist.gov',
      is_kev: true,
    },
    candidate: {
      vulnerability_id: 8,
      cve_id: 'CVE-2026-0900',
      ots_component_id: 3,
      ots_name: 'OpenSSL',
      ots_version: '3.0.0',
      match_method: 'cpe',
      match_basis: '<script>候选依据</script>',
      match_confidence: null,
      match_evidence: { range: '3.0.0' },
      first_seen_batch_id: 1,
      first_seen_batch_no: 'B-1',
      last_seen_batch_id: 2,
      last_seen_batch_no: 'B-2',
      based_on_source_modified_at: null,
    },
    candidate_disclaimer: '候选不等于产品受影响',
    draft: {
      analysis_summary: '原始分析',
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
    },
    environmental_scoring: {
      available: true,
      unavailable_reason: null,
      metrics: null,
      score: null,
      vector: null,
      calculator_version: null,
    },
    ...overrides,
  }
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState({}, '', '/system/assessments/9?from=returned')
})

describe('AssessmentDetailPage', () => {
  it('shows reason, source, candidate and editable product conclusion as text', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, {
      props: { assessmentId: 9 },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('<b>补充影响依据</b>')
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
    expect(wrapper.text()).toContain('<script>候选依据</script>')
    expect(wrapper.text()).toContain('候选不等于产品受影响')
    expect(wrapper.get<HTMLTextAreaElement>('[name="analysis_summary"]').element.value).toBe('原始分析')
    expect(wrapper.get('button[type="submit"]').text()).toContain('保存草稿')
    expect(wrapper.text()).toContain('nvd@nist.gov')
    expect(wrapper.findAll('[data-cvss-metric]').length).toBe(11)
    expect(wrapper.text()).toContain('未覆盖来源指标')
    expect(wrapper.findAll('button').some(button => button.text() === '提交审核')).toBe(true)
  })

  it('previews environmental metrics and submits metrics rather than derived values', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail({
        row_version: 2,
        draft: { ...detail().draft, cvss_metrics: { CR: 'H', IR: 'X', AR: 'X', MAV: 'X', MAC: 'X', MPR: 'X', MUI: 'X', MS: 'X', MC: 'X', MI: 'X', MA: 'X' } },
        environmental_scoring: { available: true, unavailable_reason: null, metrics: { CR: 'H', IR: 'X', AR: 'X', MAV: 'X', MAC: 'X', MPR: 'X', MUI: 'X', MS: 'X', MC: 'X', MI: 'X', MA: 'X' }, score: 9.8, vector: 'server-vector', calculator_version: 'ots-cvss31-1' },
      })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[name="cvss_metrics.CR"]').setValue('H')
    expect(wrapper.text()).toContain('未保存预览')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const payload = JSON.parse(String(fetchMock.mock.calls[1][1].body))
    expect(payload.cvss_metrics.CR).toBe('H')
    expect(payload).not.toHaveProperty('environmental_score')
    expect(payload).not.toHaveProperty('environmental_vector')
    expect(wrapper.text()).toContain('server-vector')
    expect(wrapper.text()).toContain('ots-cvss31-1')
  })

  it('shows source unavailable without editable scoring controls', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(detail({
      vulnerability: { ...detail().vulnerability, cvss31_score: null, cvss31_severity: null, cvss31_vector: null, cvss31_source: null },
      environmental_scoring: { available: false, unavailable_reason: 'SOURCE_NOT_PROVIDED', metrics: null, score: null, vector: null, calculator_version: null },
    })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    expect(wrapper.text()).toContain('来源未提供')
    expect(wrapper.find('[data-cvss-metric]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('未保存预览')
  })

  it('saves explicitly, blocks duplicate submit and adopts returned row version', async () => {
    let resolveSave: ((response: Response) => void) | undefined
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockReturnValueOnce(new Promise<Response>(resolve => { resolveSave = resolve }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[name="analysis_summary"]').setValue('更新后的分析')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)
    expect(wrapper.text()).toContain('正在保存')
    const request = fetchMock.mock.calls[1][1] as RequestInit
    expect(JSON.parse(String(request.body))).toEqual(expect.objectContaining({
      row_version: 1,
      analysis_summary: '更新后的分析',
    }))

    resolveSave?.(new Response(JSON.stringify(detail({
      row_version: 2,
      draft: { ...detail().draft, analysis_summary: '更新后的分析' },
    })), { status: 200 }))
    await flushPromises()
    expect(wrapper.text()).toContain('草稿已保存')
    await wrapper.get('form').trigger('submit')
    expect(JSON.parse(String(fetchMock.mock.calls[2][1].body)).row_version).toBe(2)
  })

  it('maps field validation, retains input and focuses the first invalid field', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'ASSESSMENT_VALIDATION_ERROR',
        message: '评估草稿校验失败',
        fields: [{ path: 'applicability_basis', message: '此字段为必填项' }],
      }), { status: 422 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 }, attachTo: document.body })
    await flushPromises()
    await wrapper.get('[name="applicability"]').setValue('not_affected')
    await wrapper.get('[name="applicability_basis"]').setValue('   ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-error-for="applicability_basis"]').text()).toContain('此字段为必填项')
    expect(wrapper.get<HTMLSelectElement>('[name="applicability"]').element.value).toBe('not_affected')
    expect(document.activeElement).toBe(wrapper.get('[name="applicability_basis"]').element)
    wrapper.unmount()
  })

  it('retains local input on version conflict and refreshes only on explicit action', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'ASSESSMENT_VERSION_CONFLICT', message: '评估已被其他操作更新，请刷新',
      }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail({
        row_version: 2,
        draft: { ...detail().draft, analysis_summary: '服务器新值' },
      })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()
    await wrapper.get('[name="analysis_summary"]').setValue('本地未保存值')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get<HTMLTextAreaElement>('[name="analysis_summary"]').element.value).toBe('本地未保存值')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('评估已被其他操作更新，请刷新')
    await wrapper.get('[data-action="refresh-server"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(wrapper.get<HTMLTextAreaElement>('[name="analysis_summary"]').element.value).toBe('服务器新值')
  })

  it('refreshes a superseded revision through the current id returned by the server', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'ASSESSMENT_NOT_EDITABLE', message: '评估当前不可编辑', current_revision_id: 10,
      }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail({
        assessment_id: 10, revision_no: 2, parent_revision_id: 9,
        current_revision_id: 10, status: 'returned', row_version: 1,
      })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    await wrapper.get('[data-action="refresh-server"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/assessments/10')
    expect(wrapper.text()).toContain('REV 2')
  })

  it('renders server-declared read-only state without a save action', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(detail({
      status: 'submitted', editable: false, return_reason: null,
    })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    expect(wrapper.text()).toContain('当前评估为只读状态')
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
    expect(wrapper.get<HTMLTextAreaElement>('[name="analysis_summary"]').element.disabled).toBe(true)
  })

  it('confirms submission once and adopts the server submitted state', async () => {
    const submitted = detail({
      status: 'submitted', editable: false, row_version: 2, submitted_by: 2,
      submitted_at: '2026-09-03T10:00:00Z',
      actions: { can_submit: false, can_approve: false, can_return: false, unavailable_reason: 'ASSESSMENT_ALREADY_SUBMITTED' },
    })
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(submitted), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[data-action="submit-assessment"]').trigger('click')
    expect(wrapper.text()).toContain('提交后当前修订将冻结')
    await wrapper.get('[data-action="confirm-submit"]').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/assessments/9/submit')
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({ row_version: 1 })
    expect(wrapper.text()).toContain('评估已提交审核')
    expect(wrapper.text()).toContain('待审核')
    expect(wrapper.find('[data-action="submit-assessment"]').exists()).toBe(false)
  })

  it('lets the reviewer approve or enter a required return comment', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(detail({
      status: 'submitted', editable: false, submitted_by: 2, submitted_at: '2026-09-03T10:00:00Z',
      actions: { can_submit: false, can_approve: true, can_return: true, unavailable_reason: null },
    })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    expect(wrapper.find('[data-action="approve-assessment"]').exists()).toBe(true)
    await wrapper.get('[data-action="return-assessment"]').trigger('click')
    await wrapper.get('[data-action="confirm-return"]').trigger('click')
    expect(wrapper.get('[data-error-for="review_comment"]').text()).toContain('必须填写')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('adopts the new current revision returned by the review action', async () => {
    const submitted = detail({
      status: 'submitted', editable: false, submitted_by: 2, row_version: 2,
      actions: {
        can_submit: false, can_approve: true, can_return: true,
        can_create_revision: false, unavailable_reason: null,
      },
      return_reason: null,
      reason_type: null,
    })
    const current = detail({
      assessment_id: 10, revision_no: 3, parent_revision_id: 9,
      current_revision_id: 10, status: 'returned', row_version: 1,
      editable: false, return_reason: '补充影响依据', reason_type: 'review_return',
      actions: {
        can_submit: false, can_approve: false, can_return: false,
        can_create_revision: false, unavailable_reason: 'ACTION_NOT_ALLOWED',
      },
    })
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(submitted), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        current_revision: current,
        reviewed_revision: {
          assessment_id: 9, revision_no: 2, status: 'returned',
          review_decision: 'returned', review_comment: '补充影响依据',
          reviewer_id: 3, reviewed_at: '2026-09-04T00:00:00Z',
        },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[data-action="return-assessment"]').trigger('click')
    await wrapper.get('[name="review_comment"]').setValue('补充影响依据')
    await wrapper.get('[data-action="confirm-return"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('REV 3')
    expect(wrapper.text()).toContain('补充影响依据')

    await wrapper.get('[data-action="load-revisions"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/assessments/10/revisions')
  })

  it('explains that an OTS-14 returned revision stays read-only', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(detail({
      status: 'returned', editable: false,
      actions: { can_submit: false, can_approve: false, can_return: false, unavailable_reason: 'RETURNED_REVISION_READ_ONLY' },
    })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    expect(wrapper.text()).toContain('已退回，等待创建新修订')
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
  })

  it('keeps the action dialog and reports reassignment or field errors', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail()), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'REVIEWER_REASSIGNMENT_REQUIRED',
        message: '提交人与当前审核人相同，请先重新分配审核人',
      }), { status: 409 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[data-action="submit-assessment"]').trigger('click')
    await wrapper.get('[data-action="confirm-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('请先重新分配审核人')
    expect(wrapper.find('[data-action="confirm-submit"]').exists()).toBe(true)
    expect(wrapper.find('[data-action="refresh-server"]').exists()).toBe(true)
  })

  it('loads revision timeline, opens read-only history and compares versions', async () => {
    const completed = detail({
      status: 'completed', editable: false, row_version: 3,
      actions: {
        can_submit: false, can_approve: false, can_return: false,
        can_create_revision: true, unavailable_reason: null,
      },
      return_reason: null,
      reason_type: null,
    })
    const historical = detail({
      assessment_id: 8, revision_no: 1, is_current: false, current_revision_id: 9,
      status: 'returned', editable: false, parent_revision_id: null,
      actions: {
        can_submit: false, can_approve: false, can_return: false,
        can_create_revision: false, unavailable_reason: null,
      },
      return_reason: '<b>历史退回意见</b>',
      reason_type: null,
    })
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(completed), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        items: [
          { assessment_id: 9, revision_no: 2, is_current: true, status: 'completed' },
          { assessment_id: 8, revision_no: 1, is_current: false, status: 'returned' },
        ],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(historical), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        base_revision_id: 8,
        target_revision_id: 9,
        changes: [{ field: 'analysis_summary', category: 'business', before: '<旧>', after: '<新>' }],
      }), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[data-action="load-revisions"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('REV 2')
    expect(wrapper.text()).toContain('REV 1')
    await wrapper.get('[data-revision-id="8"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('历史修订只读')
    expect(wrapper.get<HTMLTextAreaElement>('[name="analysis_summary"]').element.disabled).toBe(true)
    await wrapper.get('[data-action="compare-parent"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('analysis_summary')
    expect(wrapper.text()).toContain('<旧>')
    expect(wrapper.text()).toContain('<新>')
  })

  it('creates a revision from completed state and adopts the returned current id', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail({
        status: 'completed', editable: false, row_version: 3,
        actions: {
          can_submit: false, can_approve: false, can_return: false,
          can_create_revision: true, unavailable_reason: null,
        },
        return_reason: null,
        reason_type: null,
      })), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail({
        assessment_id: 10, revision_no: 3, parent_revision_id: 9,
        current_revision_id: 10, status: 'reassess', editable: true, row_version: 1,
        return_reason: null, reassess_reason: '产品配置变化', reason_type: 'manual_revision',
        actions: {
          can_submit: true, can_approve: false, can_return: false,
          can_create_revision: false, unavailable_reason: null,
        },
      })), { status: 200 }))
    const wrapper = mount(AssessmentDetailPage, { props: { assessmentId: 9 } })
    await flushPromises()

    await wrapper.get('[data-action="create-revision"]').trigger('click')
    await wrapper.get('[name="revision_reason"]').setValue('产品配置变化')
    await wrapper.get('[data-action="confirm-create-revision"]').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/assessments/9/revisions')
    expect(wrapper.text()).toContain('REV 3')
    expect(wrapper.text()).toContain('产品配置变化')
    expect(wrapper.find('button[type="submit"]').exists()).toBe(true)
  })
})
