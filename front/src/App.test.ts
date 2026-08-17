import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'
import { resetAuthenticationForTesting } from './auth'
import { isAuthenticated, router } from './router'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  resetAuthenticationForTesting()
})

async function mountAt(path: string) {
  if (router.currentRoute.value.path !== '/login') {
    await router.push('/login')
  }
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('App', () => {
  it('shows the login page when the current session is unavailable', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }),
    )

    const wrapper = await mountAt('/login')

    expect(wrapper.get('h1').text()).toBe('登录 OTS 信息维护平台')
    expect(wrapper.get('input[name="login_name"]')).toBeTruthy()
    expect(wrapper.get('input[name="password"]')).toBeTruthy()
  })

  it('redirects to the requested internal page after successful login', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
          { status: 200 },
        ),
      )

    const wrapper = await mountAt('/login?redirect=%2Fsystem')
    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('long-enough-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/system')
    expect(isAuthenticated()).toBe(true)
  })

  it('shows the generic credentials error when login is rejected', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'AUTH_INVALID_CREDENTIALS' }), { status: 401 }))

    const wrapper = await mountAt('/login')
    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('wrong-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('账号或密码错误')
  })

  it('clears local identity after logout', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    const wrapper = await mountAt('/login')
    await wrapper.get('input[name="login_name"]').setValue('admin')
    await wrapper.get('input[name="password"]').setValue('long-enough-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(isAuthenticated()).toBe(false)
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('shows an account-disabled message after a protected API response', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_USER_DISABLED' }), { status: 403 }),
    )

    const wrapper = await mountAt('/system')

    expect(wrapper.text()).toContain('账号已停用')
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
