import type { components } from './generated'

export type AuditLogPage = components['schemas']['AuditLogPageResponse']
export type AuditLogItem = components['schemas']['AuditLogListItemResponse']
export type AuditLogDetail = components['schemas']['AuditLogDetailResponse']
export type SystemOperations = components['schemas']['SystemOperationsResponse']
export type OperationComponent = components['schemas']['OperationComponentResponse']

export class AuditOperationsApiError extends Error {
  constructor(readonly code: string, readonly status: number) { super(code) }
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: 'include' })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string }
    throw new AuditOperationsApiError(payload.code ?? 'NETWORK_ERROR', response.status)
  }
  return (await response.json()) as T
}

export function listAuditLogs(filters: {
  objectType?: string
  userId?: number
  action?: string
  createdFrom?: string
  createdTo?: string
  cursor?: string
  limit?: number
} = {}): Promise<AuditLogPage> {
  const params = new URLSearchParams()
  if (filters.objectType) params.set('object_type', filters.objectType)
  if (filters.userId) params.set('user_id', String(filters.userId))
  if (filters.action) params.set('action', filters.action)
  if (filters.createdFrom) params.set('created_from', new Date(filters.createdFrom).toISOString())
  if (filters.createdTo) params.set('created_to', new Date(filters.createdTo).toISOString())
  if (filters.cursor) params.set('cursor', filters.cursor)
  params.set('limit', String(filters.limit ?? 20))
  return request<AuditLogPage>(`/api/v1/audit-logs?${params}`)
}

export function getAuditLog(id: number): Promise<AuditLogDetail> {
  return request<AuditLogDetail>(`/api/v1/audit-logs/${id}`)
}

export function getSystemOperations(): Promise<SystemOperations> {
  return request<SystemOperations>('/api/v1/system/operations')
}
