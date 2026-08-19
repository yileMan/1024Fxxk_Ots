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
    expect(authentication.feedback).toBe('')
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
