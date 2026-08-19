import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'
import { authentication, resetAuthenticationForTesting } from './auth'
import { router } from './router'

const fetchMock = vi.fn()

beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  resetAuthenticationForTesting()
  await router.push('/login')
})

describe('App', () => {
  it('shows the login page', () => {
    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.get('h1').text()).toBe('登录 OTS 信息维护平台')
    expect(wrapper.get('input[name="login_name"]')).toBeTruthy()
    expect(wrapper.get('input[name="password"]')).toBeTruthy()
  })

  it('redirects after username and password login', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
        { status: 200 },
      ),
    )
    await router.push('/login?redirect=%2Fsystem')
    const wrapper = mount(App, { global: { plugins: [router] } })

    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/system')
    expect(authentication.user?.id).toBe(1)
  })

  it('shows a stable error for invalid credentials', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_INVALID_CREDENTIALS' }), { status: 401 }),
    )
    const wrapper = mount(App, { global: { plugins: [router] } })

    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('账号或密码错误')
  })

  it('redirects unauthenticated business access to login with the original target', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }),
    )

    await router.push('/system')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/system')
    expect(authentication.feedback).toBe('')
  })

  it('allows business access after restoring the current user', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
        { status: 200 },
      ),
    )

    await router.push('/system')

    expect(router.currentRoute.value.path).toBe('/system')
    expect(authentication.user?.id).toBe(1)
  })
})
