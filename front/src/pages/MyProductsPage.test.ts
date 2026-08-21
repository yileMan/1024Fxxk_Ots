import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MyProductsPage from './MyProductsPage.vue'

const fetchMock = vi.fn()
const product = {
  id: 10,
  product_code: 'P-001',
  product_name: '监护仪',
  description: '床旁设备',
  status: 'active',
  row_version: 1,
  created_at: '2026-08-22T00:00:00',
  updated_at: '2026-08-22T00:00:00',
}
const version = {
  id: 11,
  product_id: 10,
  version_no: '2.0',
  description: null,
  primary_cvss_version: '3.1',
  owner_id: 2,
  reviewer_id: 3,
  status: 'active',
  row_version: 1,
  created_at: '2026-08-22T00:00:00',
  updated_at: '2026-08-22T00:00:00',
}
const ots = {
  id: 7,
  product_version_id: 11,
  ots_component_id: 5,
  created_by: 1,
  created_at: '2026-08-22T00:00:00',
  updated_at: '2026-08-22T00:00:00',
  ots_name: 'OpenSSL',
  ots_version: '3.0',
  official_website: 'https://openssl.org',
  is_eol: false,
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('MyProductsPage', () => {
  it('shows only authorized products, versions, and OTS without write actions', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([version]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([ots]), { status: 200 }))

    const wrapper = mount(MyProductsPage)
    await flushPromises()
    expect(wrapper.text()).toContain('监护仪')

    await wrapper.get('button[aria-label="查看监护仪版本"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('2.0')

    await wrapper.get('button[aria-label="查看版本2.0 OTS清单"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('OpenSSL')
    expect(wrapper.text()).toContain('3.0')
    expect(wrapper.find('[data-action="create-product"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('停用')
    expect(wrapper.text()).not.toContain('移除')
  })

  it('shows a clear empty-range state', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
    const wrapper = mount(MyProductsPage)
    await flushPromises()
    expect(wrapper.get('[data-state="empty"]').text()).toContain('当前没有有效的产品授权')
  })

  it('keeps service failures distinct from an empty range', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'SERVICE_UNAVAILABLE' }), { status: 503 }))
    const wrapper = mount(MyProductsPage)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('我的产品暂时不可用')
    expect(wrapper.find('[data-state="empty"]').exists()).toBe(false)
  })

  it('shows an explicit permission message when the scope has been revoked', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PRODUCT_SCOPE_FORBIDDEN' }), { status: 403 }))
    const wrapper = mount(MyProductsPage)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('产品授权已失效')
    expect(wrapper.text()).not.toContain('暂时不可用')
  })
})
