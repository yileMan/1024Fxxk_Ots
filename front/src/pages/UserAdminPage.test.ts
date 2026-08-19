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

  it('creates, edits, resets and disables users through explicit actions', async () => {
    const created = { ...userPage.items[0], id: 3, login_name: 'new-user', display_name: '新用户' }
    const edited = { ...created, display_name: '新用户（已编辑）', row_version: 2 }
    const reset = { ...edited, row_version: 3 }
    const disabled = { ...reset, status: 'disabled', row_version: 4 }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(userPage), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(created), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(edited), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(reset), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(disabled), { status: 200 }))
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    await wrapper.get('button[data-action="create-user"]').trigger('click')
    await wrapper.get('input[name="login_name"]').setValue('new-user')
    await wrapper.get('input[name="display_name"]').setValue('新用户')
    await wrapper.get('input[name="password"]').setValue('secret')
    await wrapper.findAll('input[name="roles"]')[2].setValue(true)
    await wrapper.get('form[data-form="user-editor"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('新用户')

    await wrapper.get('button[aria-label="编辑新用户"]').trigger('click')
    await wrapper.get('input[name="display_name"]').setValue('新用户（已编辑）')
    await wrapper.get('form[data-form="user-editor"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('新用户（已编辑）')

    await wrapper.get('button[aria-label="重置新用户（已编辑）密码"]').trigger('click')
    await wrapper.get('.compact-dialog input[type="password"]').setValue('new-secret')
    await wrapper.get('.compact-dialog form').trigger('submit')
    await flushPromises()

    await wrapper.get('button[aria-label="停用新用户（已编辑）"]').trigger('click')
    await wrapper.get('.warning-dialog .danger-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已停用')
  })

  it('validates an empty role selection and can retry a failed list', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('unavailable', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(userPage), { status: 200 }))
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    expect(wrapper.text()).toContain('用户目录暂时不可用')
    await wrapper.get('.text-button').trigger('click')
    await flushPromises()
    await wrapper.get('button[data-action="create-user"]').trigger('click')
    await wrapper.get('form[data-form="user-editor"]').trigger('submit')

    expect(wrapper.get('[role="alert"]').text()).toContain('请至少选择一个固定角色')
  })
})
