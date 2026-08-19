import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createUser,
  disableUser,
  getUser,
  listUsers,
  resetUserPassword,
  updateUser,
  UserApiError,
} from './users'

const fetchMock = vi.fn()
const user = {
  id: 2,
  login_name: 'zhangsan',
  display_name: '张三',
  roles: ['reviewer'] as const,
  status: 'active' as const,
  last_login_at: null,
  row_version: 1,
  created_at: '2026-08-19T12:00:00',
  updated_at: '2026-08-19T12:00:00',
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('user API client', () => {
  it('builds list filters and reads public user data', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [user], total: 1, page: 2, page_size: 10 }), { status: 200 }),
    )

    const result = await listUsers({ query: '张', status: 'active', role: 'reviewer', page: 2, pageSize: 10 })

    expect(result.total).toBe(1)
    expect(fetchMock.mock.calls[0][0]).toContain('query=%E5%BC%A0')
    expect(fetchMock.mock.calls[0][0]).toContain('role=reviewer')
  })

  it('calls every user mutation with JSON and credentials', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify(user), { status: 200 })))

    await getUser(2)
    await createUser({ login_name: 'new', display_name: '新用户', password: 'secret', roles: ['reviewer'] })
    await updateUser(2, { display_name: '张三', roles: ['admin'], row_version: 1 })
    await resetUserPassword(2, { password: 'new-secret', row_version: 2 })
    await disableUser(2, { row_version: 3 })

    expect(fetchMock).toHaveBeenCalledTimes(5)
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({ method: 'PUT', credentials: 'include' }))
    expect(fetchMock.mock.calls[4][0]).toBe('/api/v1/users/2/disable')
  })

  it('maps server and malformed failures to stable errors', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'USER_VERSION_CONFLICT' }), { status: 409 }))
      .mockResolvedValueOnce(new Response('unavailable', { status: 503 }))

    await expect(getUser(2)).rejects.toEqual(
      expect.objectContaining<Partial<UserApiError>>({ code: 'USER_VERSION_CONFLICT', status: 409 }),
    )
    await expect(getUser(2)).rejects.toEqual(
      expect.objectContaining<Partial<UserApiError>>({ code: 'NETWORK_ERROR', status: 503 }),
    )
  })
})
