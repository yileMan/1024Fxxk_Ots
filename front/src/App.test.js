import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

describe('App', () => {
  it('displays the requested text', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toBe('fuck 1024')
  })
})
