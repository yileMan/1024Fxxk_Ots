import type { components } from './generated'

export type Product = components['schemas']['ProductResponse']
export type ProductVersion = components['schemas']['ProductVersionResponse']
export type ProductPage = components['schemas']['ProductPageResponse']
export type ProductCreate = components['schemas']['ProductCreateRequest']
export type VersionCreate = components['schemas']['VersionCreateRequest']
export type ProductUpdate = components['schemas']['ProductUpdateRequest']
export type VersionUpdate = components['schemas']['VersionUpdateRequest']

export class ProductApiError extends Error {
  constructor(readonly code: string, readonly status: number) { super(code) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...init })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { code?: string }
    throw new ProductApiError(payload.code ?? 'NETWORK_ERROR', response.status)
  }
  return response.json() as Promise<T>
}

const json = (method: string, body: object): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export function listProducts(filters: { query?: string; status?: string; page?: number; pageSize?: number } = {}): Promise<ProductPage> {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.pageSize ?? 20) })
  if (filters.query) params.set('query', filters.query)
  if (filters.status) params.set('status', filters.status)
  return request<ProductPage>(`/api/v1/products?${params}`)
}
export function createProduct(payload: ProductCreate): Promise<Product> { return request('/api/v1/products', json('POST', payload)) }
export function getProduct(productId: number): Promise<Product> { return request(`/api/v1/products/${productId}`) }
export function createVersion(productId: number, payload: VersionCreate): Promise<ProductVersion> { return request(`/api/v1/products/${productId}/versions`, json('POST', payload)) }
export function listVersions(productId: number): Promise<ProductVersion[]> { return request(`/api/v1/products/${productId}/versions`) }
export function getVersion(productId: number, versionId: number): Promise<ProductVersion> { return request(`/api/v1/products/${productId}/versions/${versionId}`) }
export function disableProduct(productId: number, rowVersion: number): Promise<Product> { return request(`/api/v1/products/${productId}/disable`, json('POST', { row_version: rowVersion })) }
export function updateProduct(productId: number, payload: ProductUpdate): Promise<Product> { return request(`/api/v1/products/${productId}`, json('PUT', payload)) }
export function updateVersion(productId: number, versionId: number, payload: VersionUpdate): Promise<ProductVersion> { return request(`/api/v1/products/${productId}/versions/${versionId}`, json('PUT', payload)) }
export function disableVersion(productId: number, versionId: number, rowVersion: number): Promise<ProductVersion> { return request(`/api/v1/products/${productId}/versions/${versionId}/disable`, json('POST', { row_version: rowVersion })) }
