import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CollectorScopePage from './CollectorScopePage.vue'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:collector-scope'),
    revokeObjectURL: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

const preview = {
  scope_count: 2,
  items: [
    { ots_id: 1, ots_name: 'OpenSSL', ots_version: '3.0', official_website: 'https://openssl.org', last_covered_time: '2026-08-01T08:00:00.000Z', is_initial_collection: false },
    { ots_id: 2, ots_name: 'zlib', ots_version: '1.3', official_website: 'https://zlib.net', last_covered_time: null, is_initial_collection: true },
  ],
  comparison_baseline: { available: true, batch_no: 'B-NEW', finished_at: '2026-08-02T09:30:00Z' },
  changes: { added_ots_ids: [2], removed_ots_ids: [9], added_count: 1, removed_count: 1 },
}

describe('CollectorScopePage', () => {
  it('shows scope coverage and change evidence', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))
    const wrapper = mount(CollectorScopePage)
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('采集范围')
    expect(wrapper.text()).toContain('2 个 OTS')
    expect(wrapper.text()).toContain('B-NEW')
    expect(wrapper.text()).toContain('新增 1')
    expect(wrapper.text()).toContain('移除 1')
    expect(wrapper.text()).toContain('首次采集')
    expect(wrapper.get('a[href="https://openssl.org"]').attributes('rel')).toContain('noreferrer')
  })

  it('distinguishes no baseline, empty scope and retryable failures', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      scope_count: 0,
      items: [],
      comparison_baseline: { available: false, batch_no: null, finished_at: null },
      changes: { added_ots_ids: [], removed_ots_ids: [], added_count: 0, removed_count: 0 },
    }), { status: 200 }))
    const wrapper = mount(CollectorScopePage)
    await flushPromises()
    expect(wrapper.text()).toContain('尚无成功批次可供比较')
    expect(wrapper.text()).toContain('当前没有需要采集的 OTS')

    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'INTERNAL_ERROR' }), { status: 500 }))
    await wrapper.get('button[data-action="refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('采集范围暂时不可用')
    expect(wrapper.text()).not.toContain('当前没有需要采集的 OTS')
  })

  it('prevents duplicate downloads and refreshes after success', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))
    const wrapper = mount(CollectorScopePage)
    await flushPromises()
    fetchMock.mockResolvedValueOnce(new Response('scope_export_id,ots_id\r\n', {
      status: 200,
      headers: {
        'content-disposition': 'attachment; filename="collector_scope.csv"',
        'x-scope-export-id': '9aa5f26f-7f89-4653-8e2e-9c995e849d63',
        'x-content-sha256': 'b'.repeat(64),
      },
    })).mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))

    const download = wrapper.get('button[data-action="download"]')
    await download.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('9aa5f26f')
    expect(wrapper.text()).toContain('bbbbbbbbbbbb')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect((download.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('shows a download error without stale success evidence', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))
    const wrapper = mount(CollectorScopePage)
    await flushPromises()
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'INTERNAL_ERROR' }), { status: 500 }))

    await wrapper.get('button[data-action="download"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('下载失败')
    expect(wrapper.text()).not.toContain('导出完成')
  })
})
