import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssessmentExportPage from './AssessmentExportPage.vue'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:export'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

describe('AssessmentExportPage', () => {
  it('selects a version and OTS before previewing and downloading', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 1, product_name: '产品 A' }], total: 1, page: 1, page_size: 100 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 2, product_id: 1, version_no: '1.0', status: 'active' }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 9, ots_component_id: 3, ots_name: 'OpenSSL', ots_version: '3.0', status: 'active' }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ product_version_id: 2, product_name: '产品 A', version_no: '1.0', ots_id: 3, ots_name: 'OpenSSL', ots_version: '3.0', row_count: 4, previewed_at: '2026-09-06T00:00:00Z' }), { status: 200 }))
      .mockResolvedValueOnce(new Response('\ufeff产品,CVE\r\n产品 A,CVE-1\r\n', { status: 200, headers: { 'content-type': 'text/csv', 'content-disposition': 'attachment; filename="assessment.csv"' } }))

    const wrapper = mount(AssessmentExportPage)
    await flushPromises()
    await wrapper.get('[data-field="version"]').setValue('2')
    await flushPromises()
    await wrapper.get('[data-field="ots"]').setValue('3')
    await wrapper.get('[data-action="preview"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('4 条当前评估')
    await wrapper.get('[data-action="download"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('导出完成')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })
})
