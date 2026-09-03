import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AssessmentApiError,
  approveAssessment,
  getAssessmentDetail,
  returnAssessment,
  saveAssessmentDraft,
  submitAssessment,
  type AssessmentDraftUpdate,
} from './assessmentEditor'


const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('assessment editor API client', () => {
  it('reads detail and saves a generated-contract draft', async () => {
    const detail = { assessment_id: 9, row_version: 2, editable: true }
    const draft: AssessmentDraftUpdate = {
      row_version: 1,
      analysis_summary: '产品分析',
      trigger_conditions: null,
      affected_functions: null,
      applicability: 'pending',
      applicability_basis: null,
      product_impact: null,
      existing_controls: null,
      treatment: null,
      treatment_detail: null,
      evidence_text: null,
    }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))

    await expect(getAssessmentDetail(9)).resolves.toEqual(detail)
    await expect(saveAssessmentDraft(9, draft)).resolves.toEqual(detail)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/assessments/9', {
      credentials: 'include',
    })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/assessments/9/draft', {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    })
  })

  it('preserves stable code, status, message and field paths', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      code: 'ASSESSMENT_VALIDATION_ERROR',
      message: '评估草稿校验失败',
      fields: [{ path: 'applicability_basis', message: '此字段为必填项' }],
    }), { status: 422 }))

    await expect(getAssessmentDetail(9)).rejects.toEqual(
      expect.objectContaining<Partial<AssessmentApiError>>({
        code: 'ASSESSMENT_VALIDATION_ERROR',
        status: 422,
        message: '评估草稿校验失败',
        fields: [{ path: 'applicability_basis', message: '此字段为必填项' }],
      }),
    )
  })

  it('sends narrow generated-contract action payloads', async () => {
    const detail = { assessment_id: 9, row_version: 2 }
    fetchMock.mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(detail), { status: 200 }),
    ))

    await submitAssessment(9, { row_version: 1 })
    await approveAssessment(9, { row_version: 2 })
    await returnAssessment(9, { row_version: 2, review_comment: '补充依据' })

    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/v1/assessments/9/submit',
      '/api/v1/assessments/9/approve',
      '/api/v1/assessments/9/return',
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[2][1].body))).toEqual({
      row_version: 2,
      review_comment: '补充依据',
    })
  })
})
