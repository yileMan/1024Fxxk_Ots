import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createProduct, createVersion, disableProduct, disableVersion, getProduct, getVersion, listProducts, listVersions, ProductApiError, updateProduct, updateVersion } from './products'

const fetchMock = vi.fn()
const product = { id: 1, product_code: 'P-1', product_name: '产品', description: null, status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }
const version = { id: 2, product_id: 1, version_no: '1.0', description: null, primary_cvss_version: '3.1', owner_id: 3, reviewer_id: 4, status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })

describe('product API client', () => {
  it('builds list filters', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 2, page_size: 10 }), { status: 200 }))
    const result = await listProducts({ query: '产品', status: 'active', page: 2, pageSize: 10 })
    expect(result.total).toBe(1)
    expect(fetchMock.mock.calls[0][0]).toContain('query=%E4%BA%A7%E5%93%81')
    expect(fetchMock.mock.calls[0][0]).toContain('status=active')
  })

  it('calls every product and version resource with generated-contract payloads', async () => {
    fetchMock.mockImplementation((path: string) => Promise.resolve(new Response(JSON.stringify(path.endsWith('/versions') ? [version] : path.includes('/versions/') ? version : product), { status: 200 })))
    await getProduct(1)
    await createProduct({ product_code: 'P-1', product_name: '产品', description: null })
    await updateProduct(1, { product_code: 'P-1', product_name: '产品', description: null, row_version: 1 })
    await disableProduct(1, 2)
    await listVersions(1)
    await getVersion(1, 2)
    await createVersion(1, { version_no: '1.0', owner_id: 3, reviewer_id: 4 })
    await updateVersion(1, 2, { version_no: '1.1', description: null, owner_id: 3, reviewer_id: 4, row_version: 1 })
    await disableVersion(1, 2, 2)
    expect(fetchMock).toHaveBeenCalledTimes(9)
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({ method: 'PUT', credentials: 'include' }))
    expect(fetchMock.mock.calls[8][0]).toBe('/api/v1/products/1/versions/2/disable')
  })

  it('maps server and malformed failures', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PRODUCT_VERSION_CONFLICT' }), { status: 409 })).mockResolvedValueOnce(new Response('bad', { status: 503 }))
    await expect(getProduct(1)).rejects.toEqual(expect.objectContaining<Partial<ProductApiError>>({ code: 'PRODUCT_VERSION_CONFLICT', status: 409 }))
    await expect(getProduct(1)).rejects.toEqual(expect.objectContaining<Partial<ProductApiError>>({ code: 'NETWORK_ERROR', status: 503 }))
  })
})
