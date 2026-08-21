import type { components } from './generated'

export type Ots = components['schemas']['OtsResponse']
export type OtsPage = components['schemas']['OtsPageResponse']
export type OtsCreate = components['schemas']['OtsCreateRequest']
export type OtsUpdate = components['schemas']['OtsUpdateRequest']
export type ProductOts = components['schemas']['ProductOtsResponse']
export type OtsProductVersion = components['schemas']['OtsProductVersionResponse']
export type CsvImportResult = components['schemas']['CsvImportResultResponse']
export type CsvImportError = { row: number; field: string; reason: string }

export class OtsApiError extends Error {
  constructor(readonly code: string, readonly status: number, readonly errors: CsvImportError[] = []) { super(code) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { code?: string; errors?: CsvImportError[] }
    throw new OtsApiError(payload.code ?? 'NETWORK_ERROR', response.status, payload.errors ?? [])
  }
  return response.json() as Promise<T>
}

const json = (method: string, body: object): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export function listOts(filters: { query?: string; isEol?: boolean; page?: number; pageSize?: number } = {}): Promise<OtsPage> {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.pageSize ?? 20) })
  if (filters.query) params.set('query', filters.query)
  if (filters.isEol !== undefined) params.set('is_eol', String(filters.isEol))
  return request(`/api/v1/ots-components?${params}`)
}
export function getOts(id: number): Promise<Ots> { return request(`/api/v1/ots-components/${id}`) }
export function createOts(payload: OtsCreate): Promise<Ots> { return request('/api/v1/ots-components', json('POST', payload)) }
export function updateOts(id: number, payload: OtsUpdate): Promise<Ots> { return request(`/api/v1/ots-components/${id}`, json('PUT', payload)) }
export function listOtsProductVersions(id: number): Promise<OtsProductVersion[]> { return request(`/api/v1/ots-components/${id}/product-versions`) }
export function listProductOts(versionId: number): Promise<ProductOts[]> { return request(`/api/v1/product-versions/${versionId}/ots`) }
export function createProductOts(versionId: number, otsId: number): Promise<ProductOts> { return request(`/api/v1/product-versions/${versionId}/ots`, json('POST', { ots_component_id: otsId })) }
export async function removeProductOts(versionId: number, relationId: number): Promise<void> {
  const response = await fetch(`/api/v1/product-versions/${versionId}/ots/${relationId}`, { method: 'DELETE', credentials: 'include' })
  if (!response.ok) { const payload = await response.json().catch(() => ({})) as { code?: string }; throw new OtsApiError(payload.code ?? 'NETWORK_ERROR', response.status) }
}
export function importProductOts(versionId: number, file: File): Promise<CsvImportResult> {
  return request(`/api/v1/product-versions/${versionId}/ots/import`, { method: 'POST', headers: { 'Content-Type': 'text/csv; charset=utf-8', 'X-File-Name': file.name }, body: file })
}
async function download(path: string, fileName: string): Promise<void> {
  const response = await fetch(path, { credentials: 'include' })
  if (!response.ok) { const payload = await response.json().catch(() => ({})) as { code?: string }; throw new OtsApiError(payload.code ?? 'NETWORK_ERROR', response.status) }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = fileName; anchor.click(); URL.revokeObjectURL(url)
}
export function downloadProductOtsTemplate(): Promise<void> { return download('/api/v1/product-ots/template', 'product-ots-template.csv') }
export function exportProductOts(versionId: number): Promise<void> { return download(`/api/v1/product-versions/${versionId}/ots/export`, `product-version-${versionId}-ots.csv`) }
