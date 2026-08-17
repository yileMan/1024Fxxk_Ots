import type { components } from './generated'

export type PublicUser = components['schemas']['PublicUserResponse']

export class AuthenticationError extends Error {
  constructor(readonly code: string) {
    super(code)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string }
    throw new AuthenticationError(payload.code ?? 'NETWORK_ERROR')
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function currentUser(): Promise<PublicUser> {
  return request<PublicUser>('/api/v1/auth/me')
}

export function login(loginName: string, password: string): Promise<PublicUser> {
  return request<PublicUser>('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login_name: loginName, password }),
  })
}

export function logout(): Promise<void> {
  return request<void>('/api/v1/auth/logout', { method: 'POST' })
}
