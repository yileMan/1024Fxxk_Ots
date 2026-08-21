import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OtsAdminPage from './OtsAdminPage.vue'

const fetchMock = vi.fn()
const ots = { id: 1, ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', is_eol: false, row_version: 1, created_at: '', updated_at: '' }
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })

describe('OtsAdminPage', () => {
  it('lists, creates and edits OTS without disable or delete actions', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [ots], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
    const wrapper = mount(OtsAdminPage)
    await flushPromises()
    expect(wrapper.text()).toContain('OpenSSL')
    expect(wrapper.find('button[aria-label*="停用"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label*="删除"]').exists()).toBe(false)
    await wrapper.get('button[data-action="create-ots"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('新建 OTS')
  })

  it('preserves edits after an optimistic locking conflict', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [ots], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'OTS_VERSION_CONFLICT' }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...ots, row_version: 2 }), { status: 200 }))
    const wrapper = mount(OtsAdminPage)
    await flushPromises()
    await wrapper.get('button[aria-label="编辑OpenSSL"]').trigger('click')
    const website = wrapper.get('input[name="official_website"]')
    await website.setValue('https://draft.test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-state="conflict"]').text()).toContain('数据已被其他管理员更新')
    expect((website.element as HTMLInputElement).value).toBe('https://draft.test')
  })
})
