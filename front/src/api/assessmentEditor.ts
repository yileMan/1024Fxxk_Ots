import type { components } from './generated'

export type AssessmentDetail = components['schemas']['AssessmentDetailResponse']
export type AssessmentDraftUpdate = components['schemas']['AssessmentDraftUpdateRequest']
export type AssessmentActionRequest = components['schemas']['AssessmentActionRequest']
export type AssessmentReturnRequest = components['schemas']['AssessmentReturnRequest']
export type AssessmentFieldError = { path: string; message: string }

export class AssessmentApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly fields: AssessmentFieldError[] = [],
  ) {
    super(message)
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      code?: string
      message?: string
      fields?: AssessmentFieldError[]
    }
    throw new AssessmentApiError(
      payload.message ?? '评估服务暂时不可用',
      payload.code ?? 'NETWORK_ERROR',
      response.status,
      payload.fields ?? [],
    )
  }
  return response.json() as Promise<T>
}

export function getAssessmentDetail(assessmentId: number): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}`)
}

export function saveAssessmentDraft(
  assessmentId: number,
  draft: AssessmentDraftUpdate,
): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}/draft`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  })
}

export function submitAssessment(assessmentId: number, payload: AssessmentActionRequest): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}/submit`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function approveAssessment(assessmentId: number, payload: AssessmentActionRequest): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}/approve`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function returnAssessment(assessmentId: number, payload: AssessmentReturnRequest): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}/return`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}
