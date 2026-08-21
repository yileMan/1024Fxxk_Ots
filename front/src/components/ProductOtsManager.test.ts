import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProductOtsManager from './ProductOtsManager.vue'

const fetchMock = vi.fn()
const ots = { id: 1, ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false, row_version: 1, created_at: '', updated_at: '' }
const relation = { id: 7, product_version_id: 2, ots_component_id: 1, created_by: 1, created_at: '', updated_at: '', ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false }

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('confirm', vi.fn(() => true)) })

describe('ProductOtsManager', () => {
  it('adds and removes an OTS relation without deleting master data', async () => {
    const page = { items: [ots], total: 1, page: 1, page_size: 100 }
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(page), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(relation), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(page), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([relation]), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(page), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
    const wrapper = mount(ProductOtsManager, { props: { versionId: 2 } })
    await flushPromises()
    await wrapper.get('select').setValue('1')
    await wrapper.get('.associate button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('OpenSSL')
    await wrapper.get('button[aria-label="移除OpenSSL"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前版本尚未关联 OTS')
    expect(fetchMock.mock.calls[5][0]).toBe('/api/v1/product-versions/2/ots/7')
  })

  it('keeps the selected file and shows row-level CSV errors', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'OTS_CSV_INVALID', errors: [{ row: 2, field: 'is_eol', reason: '仅允许 true 或 false' }] }), { status: 422 }))
    const wrapper = mount(ProductOtsManager, { props: { versionId: 2 } })
    await flushPromises()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['bad'], 'bom.csv')] })
    await input.trigger('change')
    await wrapper.get('button[data-action="import-product-ots"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('第 2 行 · is_eol · 仅允许 true 或 false')
  })
})
