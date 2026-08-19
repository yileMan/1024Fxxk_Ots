import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UserAdminPage from './UserAdminPage.vue'

const fetchMock = vi.fn()
const userPage = {
  items: [
    {
      id: 2,
      login_name: 'zhangsan',
      display_name: '张三',
      roles: ['product_owner', 'reviewer'],
      status: 'active',
      last_login_at: null,
      row_version: 1,
      created_at: '2026-08-19T12:00:00',
      updated_at: '2026-08-19T12:00:00',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('UserAdminPage', () => {
  it('shows a complete user list and role-aware creation form', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(userPage), { status: 200 }))
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('用户与角色')
    expect(wrapper.text()).toContain('张三')
    expect(wrapper.text()).toContain('产品负责人')
    await wrapper.get('button[data-action="create-user"]').trigger('click')
    expect(wrapper.get('input[name="login_name"]')).toBeTruthy()
    expect(wrapper.get('input[name="password"]')).toBeTruthy()
    expect(wrapper.findAll('input[name="roles"]')).toHaveLength(3)
  })

  it('renders a dedicated permission state for 403 responses', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 'AUTH_FORBIDDEN' }), { status: 403 }),
    )
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('无权访问用户管理')
    expect(wrapper.text()).not.toContain('暂无用户')
  })

  it('keeps edited input when the server reports a version conflict', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(userPage), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 'USER_VERSION_CONFLICT' }), { status: 409 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(userPage.items[0]), { status: 200 }))
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    await wrapper.get('button[aria-label="编辑张三"]').trigger('click')
    const displayName = wrapper.get('input[name="display_name"]')
    await displayName.setValue('张三（待保存）')
    await wrapper.get('form[data-form="user-editor"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-state="conflict"]').text()).toContain('数据已被其他管理员更新')
    expect((displayName.element as HTMLInputElement).value).toBe('张三（待保存）')
  })

  it('requires confirmation before disabling an active user', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(userPage), { status: 200 }))
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    await wrapper.get('button[aria-label="停用张三"]').trigger('click')

    expect(wrapper.get('[role="dialog"]').text()).toContain('停用后将保留全部历史记录')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
