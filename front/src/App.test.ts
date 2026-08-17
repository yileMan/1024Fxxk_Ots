import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  window.history.replaceState({}, '', '/login')
})

describe('App', () => {
  it('shows the login page when the current session is unavailable', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }),
    )

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('登录 OTS 信息维护平台')
    expect(wrapper.get('input[name="login_name"]').exists()).toBe(true)
    expect(wrapper.get('input[name="password"]').exists()).toBe(true)
  })

  it('redirects to the requested internal page after successful login', async () => {
    window.history.replaceState({}, '', '/login?redirect=%2Fsystem')
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
          { status: 200 },
        ),
      )

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('long-enough-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(window.location.pathname).toBe('/system')
  })

  it('shows an account-disabled message after a protected API response', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_USER_DISABLED' }), { status: 403 }),
    )

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('账号已停用')
    expect(window.location.pathname).toBe('/login')
  })
})
