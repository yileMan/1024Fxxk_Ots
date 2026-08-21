import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthenticationError, login } from './api/auth'
import {
  authentication,
  resetAuthenticationForTesting,
  restoreAuthentication,
} from './auth'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  resetAuthenticationForTesting()
})

describe('authentication state', () => {
  it('shares one current-user request and keeps only public identity in memory', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
        { status: 200 },
      ),
    )

    const [first, second] = await Promise.all([restoreAuthentication(), restoreAuthentication()])
    const cached = await restoreAuthentication()

    expect(first?.login_name).toBe('admin')
    expect(second?.roles).toEqual(['admin'])
    expect(cached?.id).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(authentication.scope?.is_global).toBe(true)
    expect(authentication.feedback).toBe('')
  })

  it('loads an ordinary user scope summary into memory without browser persistence', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ is_global: false, scopes: [], effective_product_ids: [10], effective_version_ids: [11] }),
          { status: 200 },
        ),
      )

    await restoreAuthentication()

    expect(authentication.scope?.effective_version_ids).toEqual([11])
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/scopes/me')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('reports an unavailable user-id cookie without restoring identity', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }),
    )

    await expect(restoreAuthentication()).resolves.toBeNull()
    expect(authentication.user).toBeNull()
    expect(authentication.feedback).toBe('')
  })

  it('maps malformed API failures to a stable client error', async () => {
    fetchMock.mockResolvedValue(new Response('unavailable', { status: 503 }))

    await expect(login('admin', 'long-enough-password')).rejects.toEqual(
      expect.objectContaining<Partial<AuthenticationError>>({ code: 'NETWORK_ERROR' }),
    )
  })
})
