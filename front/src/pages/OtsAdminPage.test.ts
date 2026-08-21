import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OtsAdminPage from './OtsAdminPage.vue'

const fetchMock = vi.fn()
const ots = { id: 1, ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false, row_version: 1, created_at: '', updated_at: '' }
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })

describe('OtsAdminPage', () => {
  it('lists, creates and edits OTS without disable or delete actions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [ots], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...ots, id: 2, ots_name: 'zlib' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [ots], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ product_ots_id: 7, product_id: 3, product_code: 'P-1', product_name: '终端产品', product_version_id: 4, version_no: '1.0', status: 'active' }]), { status: 200 }))
    const wrapper = mount(OtsAdminPage)
    await flushPromises()
    expect(wrapper.text()).toContain('OpenSSL')
    expect(wrapper.find('button[aria-label*="停用"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label*="删除"]').exists()).toBe(false)
    await wrapper.get('button[data-action="create-ots"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('新建 OTS')
    await wrapper.get('input[name="ots_name"]').setValue('zlib')
    await wrapper.get('input[name="ots_version"]').setValue('1.3')
    await wrapper.get('input[name="official_website"]').setValue('https://zlib.net')
    await wrapper.get('form[data-form="ots-editor"]').trigger('submit')
    await flushPromises()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/ots-components')
    await wrapper.get('button[aria-label="查看OpenSSL关联产品"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('终端产品')
  })

  it('preserves edits after an optimistic locking conflict', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [ots], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'OTS_VERSION_CONFLICT' }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...ots, row_version: 2 }), { status: 200 }))
    const wrapper = mount(OtsAdminPage)
    await flushPromises()
    await wrapper.get('button[aria-label="编辑OpenSSL"]').trigger('click')
    const website = wrapper.get('input[name="official_website"]')
    await website.setValue('https://draft.test')
    await wrapper.get('form[data-form="ots-editor"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-state="conflict"]').text()).toContain('数据已被其他管理员更新')
    expect((website.element as HTMLInputElement).value).toBe('https://draft.test')
  })
})
