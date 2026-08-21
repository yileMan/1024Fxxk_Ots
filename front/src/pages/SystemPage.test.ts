import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SystemPage from './SystemPage.vue'
import { authentication } from '../auth'

describe('SystemPage', () => {
  it('shows the four current admin modules using the existing card language', () => {
    authentication.user = { id: 1, login_name: 'admin', display_name: '管理员', roles: ['admin'] }
    const wrapper = mount(SystemPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(wrapper.findAll('.module-card').map(card => card.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('产品管理'), expect.stringContaining('OTS 主数据'), expect.stringContaining('用户与角色'), expect.stringContaining('服务状态'),
    ]))
  })
})
