import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductScopeEditor from './ProductScopeEditor.vue'

const fetchMock = vi.fn()
const products = {
  items: [{ id: 10, product_code: 'P-001', product_name: '监护仪', description: null, status: 'active', row_version: 1 }],
  total: 1,
  page: 1,
  page_size: 100,
}
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

describe('ProductScopeEditor', () => {
  it('loads products and renders an explicit empty authorization state', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(summary), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(products), { status: 200 }))

    const wrapper = mount(ProductScopeEditor, { props: { userId: 2, userDisplayName: '张三' } })
    await flushPromises()

    expect(wrapper.get('h2').text()).toContain('张三')
    expect(wrapper.get('[data-state="empty"]').text()).toContain('尚未配置产品范围')
    expect(wrapper.get('select[name="product_id"]')).toBeTruthy()
  })

  it('grants a product scope and refreshes the effective summary', async () => {
    const granted = {
      id: 1,
      user_id: 2,
      scope_type: 'product',
      product_id: 10,
      product_version_id: null,
      scope_key: 'product:10',
      created_by: 1,
      created_at: '2026-08-21T00:00:00',
      updated_at: '2026-08-21T00:00:00',
      is_effective: true,
    }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(summary), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(products), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(granted), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...summary, scopes: [granted], effective_product_ids: [10] }), { status: 200 }))

    const wrapper = mount(ProductScopeEditor, { props: { userId: 2, userDisplayName: '张三' } })
    await flushPromises()
    await wrapper.get('select[name="product_id"]').setValue('10')
    await wrapper.get('form[data-form="scope-grant"]').trigger('submit')
    await flushPromises()

    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/users/2/scopes')
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      scope_type: 'product',
      product_id: 10,
      product_version_id: null,
    })
    expect(wrapper.text()).toContain('覆盖该产品全部有效版本')
  })

  it('shows a dedicated forbidden state for scope API 403 responses', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_FORBIDDEN' }), { status: 403 }),
    )

    const wrapper = mount(ProductScopeEditor, { props: { userId: 2, userDisplayName: '张三' } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('无权配置产品范围')
  })
})
