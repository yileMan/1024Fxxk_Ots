import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('displays the platform heading', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('OTS 信息维护平台')
    expect(wrapper.text()).toContain('系统健康')
  })
})
