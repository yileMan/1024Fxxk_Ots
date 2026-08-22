import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import SystemPage from './SystemPage.vue'
import { authentication, resetAuthenticationForTesting } from '../auth'

describe('SystemPage', () => {
  beforeEach(() => resetAuthenticationForTesting())

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
})
