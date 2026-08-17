import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthenticationError, login } from './api/auth'
import {
  authentication,
  clearAuthentication,
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

    expect(first?.login_name).toBe('admin')
    expect(second?.roles).toEqual(['admin'])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(authentication.feedback).toBe('')
  })

  it('clears identity with a displayable message', () => {
    clearAuthentication('会话已失效')

    expect(authentication.user).toBeNull()
    expect(authentication.feedback).toBe('会话已失效')
  })

  it('maps malformed API failures to a stable client error', async () => {
    fetchMock.mockResolvedValue(new Response('unavailable', { status: 503 }))

    await expect(login('admin', 'long-enough-password')).rejects.toEqual(
      expect.objectContaining<Partial<AuthenticationError>>({ code: 'NETWORK_ERROR' }),
    )
  })
})
