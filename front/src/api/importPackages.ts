import type { components } from './generated'


export type ImportPackageResult = components['schemas']['ImportPackageResponse']

export class ImportPackageApiError extends Error {
  constructor(readonly code: string, readonly status: number) {
    super(code)
  }
}

async function errorFrom(response: Response): Promise<ImportPackageApiError> {
  const payload = await response.json().catch(() => ({})) as { code?: string }
  return new ImportPackageApiError(payload.code ?? 'NETWORK_ERROR', response.status)
}

export async function validateImportPackage(file: File): Promise<ImportPackageResult> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/v1/import-packages/validate', {
    method: 'POST',
    credentials: 'include',
    body,
  })
  if (!response.ok) throw await errorFrom(response)
  return response.json() as Promise<ImportPackageResult>
}

export async function getImportPackage(batchId: number): Promise<ImportPackageResult> {
  const response = await fetch(`/api/v1/import-packages/${batchId}`, { credentials: 'include' })
  if (!response.ok) throw await errorFrom(response)
  return response.json() as Promise<ImportPackageResult>
}

export async function confirmImportPackage(batchId: number): Promise<ImportPackageResult> {
  const response = await fetch(`/api/v1/import-packages/${batchId}/confirm`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await errorFrom(response)
  return response.json() as Promise<ImportPackageResult>
}

function responseFileName(response: Response): string {
  const disposition = response.headers.get('content-disposition') ?? ''
  return /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? 'package_validation_errors.csv'
}

export async function downloadPackageErrors(batchId: number): Promise<string> {
  const response = await fetch(`/api/v1/import-packages/${batchId}/errors`, { credentials: 'include' })
  if (!response.ok) throw await errorFrom(response)
  const fileName = responseFileName(response)
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
