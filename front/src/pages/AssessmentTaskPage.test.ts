import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AssessmentTaskPage from './AssessmentTaskPage.vue'


const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState({}, '', '/system/assessments/tasks?queue=returned&page=1')
})

describe('AssessmentTaskPage', () => {
  it('restores the queue from URL and shows scoped task context', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      items: [{
        assessment_id: 9, vulnerability_id: 8, revision_no: 2, status: 'returned', cve_id: 'CVE-2026-0900',
        product_id: 1, product_name: '监护仪', product_version_id: 2, version_no: '3.0',
        product_ots_id: 3, ots_component_id: 4, ots_name: 'OpenSSL', ots_version: '3.0.0',
        owner_id: 5, reviewer_id: 6, source_severity: 'HIGH', updated_at: '2026-09-01T08:00:00Z',
      }], total: 1, page: 1, page_size: 20,
    }), { status: 200 }))

    const wrapper = mount(AssessmentTaskPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/assessments/tasks?queue=returned&page=1&page_size=20',
      { credentials: 'include' },
    )
    expect(wrapper.text()).toContain('已退回')
    expect(wrapper.text()).toContain('CVE-2026-0900')
    expect(wrapper.text()).toContain('监护仪 3.0')
    expect(wrapper.text()).toContain('OpenSSL 3.0.0')
  })

  it('keeps permission failures distinct from empty results', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'VULNERABILITY_FORBIDDEN' }), { status: 403 }))
    const wrapper = mount(AssessmentTaskPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('无权查看')
    expect(wrapper.find('[data-state="empty"]').exists()).toBe(false)
  })

  it('switches queue and page through recoverable URL state', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 41, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 41, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 41, page: 2, page_size: 20 }), { status: 200 }))
    const wrapper = mount(AssessmentTaskPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    await wrapper.get('.queue-tabs a').trigger('click')
    await flushPromises()
    expect(window.location.search).toBe('?queue=pending&page=1')
    expect(String(fetchMock.mock.calls[1][0])).toContain('queue=pending')

    window.history.replaceState({}, '', '/system/assessments/tasks?queue=returned&page=1')
    const pagedWrapper = mount(AssessmentTaskPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    await pagedWrapper.get('.pagination button:last-child').trigger('click')
    await flushPromises()
    expect(window.location.search).toBe('?queue=returned&page=2')
    expect(String(fetchMock.mock.calls[3][0])).toContain('page=2')
  })
})
