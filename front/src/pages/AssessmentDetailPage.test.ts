import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssessmentDetailPage from './AssessmentDetailPage.vue'


const fetchMock = vi.fn()

function detail(overrides: Record<string, unknown> = {}) {
  return {
    assessment_id: 9,
    revision_no: 2,
    is_current: true,
    status: 'returned',
    owner_id: 2,
    row_version: 1,
    editable: true,
    return_reason: '<b>补充影响依据</b>',
    reassess_reason: null,
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
    expect(wrapper.find('[name="environmental_score"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('提交审核')
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
})
