import type { components } from './generated'

export type AssessmentDetail = components['schemas']['AssessmentDetailResponse']
export type AssessmentDraftUpdate = components['schemas']['AssessmentDraftUpdateRequest']
export type AssessmentActionRequest = components['schemas']['AssessmentActionRequest']
export type AssessmentReturnRequest = components['schemas']['AssessmentReturnRequest']
export type AssessmentReturnResponse = components['schemas']['AssessmentReturnResponse']
export type AssessmentRevisionCreateRequest = components['schemas']['AssessmentRevisionCreateRequest']
export type AssessmentRevisionHistory = components['schemas']['AssessmentRevisionHistoryResponse']
export type AssessmentRevisionComparison = components['schemas']['AssessmentRevisionComparisonResponse']
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

export function returnAssessment(assessmentId: number, payload: AssessmentReturnRequest): Promise<AssessmentReturnResponse> {
  return request(`/api/v1/assessments/${assessmentId}/return`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function createAssessmentRevision(
  assessmentId: number,
  payload: AssessmentRevisionCreateRequest,
): Promise<AssessmentDetail> {
  return request(`/api/v1/assessments/${assessmentId}/revisions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

export function getAssessmentRevisionHistory(
  assessmentId: number,
): Promise<AssessmentRevisionHistory> {
  return request(`/api/v1/assessments/${assessmentId}/revisions`)
}

export function compareAssessmentRevisions(
  assessmentId: number,
  baseRevisionId: number,
  targetRevisionId: number,
): Promise<AssessmentRevisionComparison> {
  const parameters = new URLSearchParams({
    base_revision_id: String(baseRevisionId),
    target_revision_id: String(targetRevisionId),
  })
  return request(`/api/v1/assessments/${assessmentId}/revision-comparison?${parameters}`)
}
