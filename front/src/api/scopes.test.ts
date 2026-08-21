import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  currentScopeSummary,
  grantUserScope,
  listUserScopes,
  revokeUserScope,
  ScopeApiError,
} from './scopes'

const fetchMock = vi.fn()
const summary = {
  is_global: false,
  scopes: [],
  effective_product_ids: [],
  effective_version_ids: [],
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('scope API client', () => {
  it('uses generated-contract paths and payloads', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(summary), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(summary), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await currentScopeSummary()
    await listUserScopes(2)
    await grantUserScope(2, { scope_type: 'product', product_id: 10, product_version_id: null })
    await revokeUserScope(2, 1)

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/scopes/me',
      '/api/v1/users/2/scopes',
      '/api/v1/users/2/scopes',
      '/api/v1/users/2/scopes/1',
    ])
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      scope_type: 'product',
      product_id: 10,
      product_version_id: null,
    })
    expect(fetchMock.mock.calls[3][1]).toEqual(expect.objectContaining({ method: 'DELETE', credentials: 'include' }))
  })

  it('maps 403 and malformed failures to stable errors', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PRODUCT_SCOPE_FORBIDDEN' }), { status: 403 }))
      .mockResolvedValueOnce(new Response('bad', { status: 503 }))

    await expect(currentScopeSummary()).rejects.toEqual(
      expect.objectContaining<Partial<ScopeApiError>>({ code: 'PRODUCT_SCOPE_FORBIDDEN', status: 403 }),
    )
    await expect(currentScopeSummary()).rejects.toEqual(
      expect.objectContaining<Partial<ScopeApiError>>({ code: 'NETWORK_ERROR', status: 503 }),
    )
  })
})
