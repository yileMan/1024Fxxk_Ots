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
    expect(wrapper.text()).toContain('内网可信工作台')
    expect(wrapper.text()).toContain('访问边界')
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

  it('routes a non-admin identity to an explicit forbidden page', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] }),
        { status: 200 },
      ),
    )

    await router.push('/system/users')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(wrapper.get('h1').text()).toBe('没有访问权限')
  })

  it('uses a left sidebar with seven ordered navigation items for administrators', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
        { status: 200 },
      ),
    )
    await router.push('/system')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const sidebar = wrapper.get('aside.app-sidebar')
    expect(sidebar.findAll('nav a').map((link) => link.text())).toEqual([
      '工作台',
      '产品管理',
      'OTS',
      '采集范围',
      '数据包导入',
      '用户与角色',
      '运行状态',
    ])
    expect(sidebar.get('a[aria-current="page"]').text()).toBe('工作台')
  })

  it('shows a scoped read-only product entry and hides every admin entry for an authorized user', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 2, login_name: 'owner', display_name: '产品负责人', roles: ['product_owner'] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        is_global: false,
        scopes: [],
        effective_product_ids: [10],
        effective_version_ids: [11],
      }), { status: 200 }))
    await router.push('/system')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('aside.app-sidebar').findAll('nav a').map((link) => link.text())).toEqual([
      '工作台',
      '我的产品',
      '运行状态',
    ])
  })

  it('clears in-memory identity and returns to login after logout', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    await router.push('/system')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('button[aria-label="退出登录"]').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/logout')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(authentication.user).toBeNull()
  })

  it('keeps the current identity and shows feedback when logout fails', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'NETWORK_ERROR' }), { status: 503 }))
    await router.push('/system')
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('button[aria-label="退出登录"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/system')
    expect(authentication.user?.id).toBe(1)
    expect(wrapper.text()).toContain('退出失败，请检查网络后重试')
  })
})
