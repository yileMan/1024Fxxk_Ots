import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createOts, createProductOts, exportProductOts, importProductOts, listOts, listProductOts, OtsApiError, removeProductOts, updateOts } from './ots'

const fetchMock = vi.fn()
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() }) })

describe('OTS API client', () => {
  it('uses generated-contract JSON resources', async () => {
    const ots = { id: 1, ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false, row_version: 1, created_at: '', updated_at: '' }
    fetchMock.mockImplementation((path: string) => Promise.resolve(new Response(JSON.stringify(path.includes('/product-versions/') ? [] : path.includes('?') ? { items: [ots], total: 1, page: 1, page_size: 20 } : ots), { status: path.endsWith('/ots-components') ? 201 : 200 })))
    await listOts({ query: 'Open', isEol: false })
    await createOts({ ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false })
    await updateOts(1, { ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false, row_version: 1 })
    await listProductOts(2)
    await createProductOts(2, 1)
    await removeProductOts(2, 3)
    expect(fetchMock.mock.calls[0][0]).toContain('is_eol=false')
    expect(fetchMock.mock.calls[5][1]).toEqual(expect.objectContaining({ method: 'DELETE', credentials: 'include' }))
  })

  it('keeps structured CSV errors and supports file transfer', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'OTS_CSV_INVALID', errors: [{ row: 2, field: 'is_eol', reason: '非法值' }] }), { status: 422 }))
      .mockResolvedValueOnce(new Response('ots_name,ots_version,official_website,is_eol\n', { status: 200, headers: { 'content-type': 'text/csv' } }))
    await expect(importProductOts(2, new File(['bad'], 'bom.csv'))).rejects.toEqual(expect.objectContaining<Partial<OtsApiError>>({ code: 'OTS_CSV_INVALID', errors: [{ row: 2, field: 'is_eol', reason: '非法值' }] }))
    await exportProductOts(2)
  })
})
