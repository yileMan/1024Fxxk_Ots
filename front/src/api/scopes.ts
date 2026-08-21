import type { components } from './generated'

export type ProductScope = components['schemas']['ScopeResponse']
export type ProductScopeSummary = components['schemas']['ScopeSummaryResponse']
export type ProductScopeGrant = components['schemas']['ScopeGrantRequest']

export class ScopeApiError extends Error {
  constructor(readonly code: string, readonly status: number) {
    super(code)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string }
    throw new ScopeApiError(payload.code ?? 'NETWORK_ERROR', response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function currentScopeSummary(): Promise<ProductScopeSummary> {
  return request<ProductScopeSummary>('/api/v1/scopes/me')
}

export function listUserScopes(userId: number): Promise<ProductScopeSummary> {
  return request<ProductScopeSummary>(`/api/v1/users/${userId}/scopes`)
}

export function grantUserScope(userId: number, payload: ProductScopeGrant): Promise<ProductScope> {
  return request<ProductScope>(`/api/v1/users/${userId}/scopes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function revokeUserScope(userId: number, scopeId: number): Promise<void> {
  return request<void>(`/api/v1/users/${userId}/scopes/${scopeId}`, { method: 'DELETE' })
}
