import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemPage from './SystemPage.vue'
import { authentication, resetAuthenticationForTesting } from '../auth'

describe('SystemPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    resetAuthenticationForTesting()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('shows the current admin modules using the existing card language', () => {
    authentication.user = { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] }
    const wrapper = mount(SystemPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(wrapper.findAll('.module-card').map(card => card.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('产品管理'), expect.stringContaining('OTS 主数据'), expect.stringContaining('用户与角色'), expect.stringContaining('采集范围'), expect.stringContaining('服务状态'),
    ]))
  })

  it('shows the scoped product workspace to an authorized ordinary user', () => {
    authentication.user = { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] }
    authentication.scope = { is_global: false, scopes: [], effective_product_ids: [10], effective_version_ids: [11] }
    authentication.scopeInitialized = true
    const wrapper = mount(SystemPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(wrapper.findAll('.module-card').map(card => card.text())).toEqual([
      expect.stringContaining('我的产品'),
      expect.stringContaining('服务状态'),
    ])
  })

  it('shows live task cards and the admin import/coverage summary', async () => {
    authentication.user = { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ pending_count: 2, returned_count: 1, reassess_count: 3, submitted_count: 4 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        latest_succeeded: { id: 12, batch_no: 'B-12', status: 'succeeded', finished_at: '2026-09-01T08:00:00Z', error_code: null, error_count: 0 },
        latest_failed: null, last_successful_import_at: '2026-09-01T08:00:00Z',
        coverage_status: 'not_provided', last_covered_time: null,
      }), { status: 200 }))

    const wrapper = mount(SystemPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('待产品评估2')
    expect(wrapper.text()).toContain('待复评3')
    expect(wrapper.text()).toContain('待审核4')
    expect(wrapper.text()).toContain('B-12')
    expect(wrapper.text()).toContain('覆盖截止时间未提供')
  })

  it('keeps task counts above the decorative card frame', async () => {
    authentication.user = { id: 2, login_name: 'owner', display_name: '负责人', roles: ['product_owner'] }
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ pending_count: 2, returned_count: 1, reassess_count: 3, submitted_count: 4 }), { status: 200 }))

    const wrapper = mount(SystemPage, { attachTo: document.body, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    const countStyle = getComputedStyle(wrapper.get('.task-card h2 strong').element)
    expect(countStyle.position).toBe('relative')
    expect(countStyle.zIndex).toBe('1')
    wrapper.unmount()
  })
})
