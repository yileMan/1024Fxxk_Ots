import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AssessmentApiError,
  getAssessmentDetail,
  saveAssessmentDraft,
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
})
