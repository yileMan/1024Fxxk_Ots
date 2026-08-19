import type { components } from './generated'

export type ManagedUser = components['schemas']['UserResponse']
export type UserPage = components['schemas']['UserPageResponse']
export type UserCreate = components['schemas']['UserCreateRequest']
export type UserUpdate = components['schemas']['UserUpdateRequest']
export type PasswordReset = components['schemas']['PasswordResetRequest']
export type UserDisable = components['schemas']['UserDisableRequest']
export type UserRole = ManagedUser['roles'][number]

export class UserApiError extends Error {
  constructor(readonly code: string, readonly status: number) {
    super(code)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string }
    throw new UserApiError(payload.code ?? 'NETWORK_ERROR', response.status)
  }
  return (await response.json()) as T
}

function jsonRequest(method: string, body: object): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function listUsers(filters: {
  query?: string
  status?: string
  role?: string
  page?: number
  pageSize?: number
} = {}): Promise<UserPage> {
  const params = new URLSearchParams()
  if (filters.query) params.set('query', filters.query)
  if (filters.status) params.set('status', filters.status)
  if (filters.role) params.set('role', filters.role)
  params.set('page', String(filters.page ?? 1))
  params.set('page_size', String(filters.pageSize ?? 20))
  return request<UserPage>(`/api/v1/users?${params}`)
}

export function getUser(userId: number): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}`)
}

export function createUser(payload: UserCreate): Promise<ManagedUser> {
  return request<ManagedUser>('/api/v1/users', jsonRequest('POST', payload))
}

export function updateUser(userId: number, payload: UserUpdate): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}`, jsonRequest('PUT', payload))
}

export function resetUserPassword(userId: number, payload: PasswordReset): Promise<ManagedUser> {
  return request<ManagedUser>(
    `/api/v1/users/${userId}/reset-password`,
    jsonRequest('POST', payload),
  )
}

export function disableUser(userId: number, payload: UserDisable): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}/disable`, jsonRequest('POST', payload))
}
