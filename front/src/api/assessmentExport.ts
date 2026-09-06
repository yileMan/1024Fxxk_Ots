import type { components } from './generated'

export type AssessmentExportPreview = components['schemas']['AssessmentExportPreviewResponse']

export class AssessmentExportApiError extends Error {
  constructor(readonly code: string, readonly status: number) { super(code) }
}

async function errorFrom(response: Response): Promise<AssessmentExportApiError> {
  const payload = await response.json().catch(() => ({})) as { code?: string }
  return new AssessmentExportApiError(payload.code ?? 'NETWORK_ERROR', response.status)
}

function path(kind: 'preview' | 'csv', versionId: number, otsId: number): string {
  const params = new URLSearchParams({ product_version_id: String(versionId), ots_id: String(otsId) })
  return `/api/v1/assessment-exports/${kind}?${params}`
}

export async function previewAssessmentExport(versionId: number, otsId: number): Promise<AssessmentExportPreview> {
  const response = await fetch(path('preview', versionId, otsId), { credentials: 'include' })
  if (!response.ok) throw await errorFrom(response)
  return response.json() as Promise<AssessmentExportPreview>
}

export async function downloadAssessmentExport(versionId: number, otsId: number, signal?: AbortSignal): Promise<string> {
  const response = await fetch(path('csv', versionId, otsId), { credentials: 'include', signal })
  if (!response.ok || !(response.headers.get('content-type') ?? '').includes('text/csv')) throw await errorFrom(response)
  const disposition = response.headers.get('content-disposition') ?? ''
  const fileName = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? 'assessment_export.csv'
  const url = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = fileName
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
  return fileName
}
