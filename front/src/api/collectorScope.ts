import type { components } from './generated'

export type CollectorScopePreview = components['schemas']['CollectorScopePreviewResponse']

export type CollectorScopeDownloadEvidence = {
  fileName: string
  scopeExportId: string
  sha256: string
}

export class CollectorScopeApiError extends Error {
  constructor(readonly code: string, readonly status: number) {
    super(code)
  }
}

async function errorFrom(response: Response): Promise<CollectorScopeApiError> {
  const payload = await response.json().catch(() => ({})) as { code?: string }
  return new CollectorScopeApiError(payload.code ?? 'NETWORK_ERROR', response.status)
}

export async function getCollectorScope(): Promise<CollectorScopePreview> {
  const response = await fetch('/api/v1/collector-scope', { credentials: 'include' })
  if (!response.ok) throw await errorFrom(response)
  return response.json() as Promise<CollectorScopePreview>
}

function responseFileName(response: Response): string {
  const disposition = response.headers.get('content-disposition') ?? ''
  const match = /filename="?([^";]+)"?/i.exec(disposition)
  return match?.[1] ?? 'collector_scope.csv'
}

export async function downloadCollectorScope(): Promise<CollectorScopeDownloadEvidence> {
  const response = await fetch('/api/v1/collector-scope/export', { credentials: 'include' })
  if (!response.ok) throw await errorFrom(response)
  const fileName = responseFileName(response)
  const scopeExportId = response.headers.get('x-scope-export-id') ?? ''
  const sha256 = response.headers.get('x-content-sha256') ?? ''
  const url = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = fileName
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
  return { fileName, scopeExportId, sha256 }
}
