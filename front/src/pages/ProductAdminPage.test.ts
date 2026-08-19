import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductAdminPage from './ProductAdminPage.vue'

const fetchMock = vi.fn()
const product = { id: 1, product_code: 'OTS-001', product_name: '终端产品', description: null, status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }
const version = { id: 2, product_id: 1, version_no: '1.0', description: null, primary_cvss_version: '3.1', owner_id: 3, reviewer_id: 4, status: 'active', row_version: 1, created_at: '2026-08-19T12:00:00', updated_at: '2026-08-19T12:00:00' }

beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })

describe('ProductAdminPage', () => {
  it('creates a product and its initial version with the two-step wizard', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 3, display_name: '负责人', roles: ['product_owner'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 4, display_name: '审核人', roles: ['reviewer'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(product), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(version), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()

    await wrapper.get('button[data-action="create-product"]').trigger('click')
    await wrapper.get('input[name="product_code"]').setValue('OTS-001')
    await wrapper.get('input[name="product_name"]').setValue('终端产品')
    await wrapper.get('form[data-form="product-editor"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('第 2 步')

    await wrapper.get('input[name="version_no"]').setValue('1.0')
    await wrapper.get('select[name="owner_id"]').setValue('3')
    await wrapper.get('select[name="reviewer_id"]').setValue('4')
    await wrapper.get('form[data-form="product-editor"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('终端产品')
  })

  it('shows version records after opening version maintenance', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 3, display_name: '负责人', roles: ['product_owner'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 4, display_name: '审核人', roles: ['reviewer'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([version]), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()

    await wrapper.get('button[aria-label="维护终端产品版本"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="dialog"]').text()).toContain('版本维护')
    expect(wrapper.text()).toContain('1.0')
  })

  it('creates a second version from version maintenance', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 3, display_name: '负责人', roles: ['product_owner'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 4, display_name: '审核人', roles: ['reviewer'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([version]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...version, id: 5, version_no: '2.0' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([version, { ...version, id: 5, version_no: '2.0' }]), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()
    await wrapper.get('button[aria-label="维护终端产品版本"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[data-action="create-version"]').trigger('click')
    await wrapper.get('input[name="version_no"]').setValue('2.0')
    await wrapper.get('select[name="owner_id"]').setValue('3')
    await wrapper.get('select[name="reviewer_id"]').setValue('4')
    await wrapper.get('form[data-form="version-editor"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('2.0')
  })

  it('keeps product edits after an optimistic locking conflict', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PRODUCT_VERSION_CONFLICT' }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...product, row_version: 2 }), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()
    await wrapper.get('button[aria-label="编辑终端产品"]').trigger('click')
    const name = wrapper.get('input[name="product_name"]')
    await name.setValue('终端产品（待保存）')
    await wrapper.get('form[data-form="product-editor"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-state="conflict"]').text()).toContain('数据已被其他管理员更新')
    expect((name.element as HTMLInputElement).value).toBe('终端产品（待保存）')
  })

  it('keeps version edits after an optimistic locking conflict', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 3, display_name: '负责人', roles: ['product_owner'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: 4, display_name: '审核人', roles: ['reviewer'], status: 'active' }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([version]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PRODUCT_VERSION_CONFLICT' }), { status: 409 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...version, row_version: 2 }), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()
    await wrapper.get('button[aria-label="维护终端产品版本"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="编辑版本1.0"]').trigger('click')
    const versionNo = wrapper.get('input[name="version_no"]')
    await versionNo.setValue('1.1-draft')
    await wrapper.get('form[data-form="version-editor"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-state="conflict"]').text()).toContain('数据已被其他管理员更新')
    expect((versionNo.element as HTMLInputElement).value).toBe('1.1-draft')
  })

  it('asks for confirmation before disabling a product', async () => {
    const confirmMock = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
    vi.stubGlobal('confirm', confirmMock)
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [product], total: 1, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...product, status: 'disabled', row_version: 2 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ ...product, status: 'disabled', row_version: 2 }], total: 1, page: 1, page_size: 20 }), { status: 200 }))
    const wrapper = mount(ProductAdminPage)
    await flushPromises()
    const disableButton = wrapper.get('button[aria-label="停用终端产品"]')

    await disableButton.trigger('click')
    expect(fetchMock).toHaveBeenCalledTimes(3)
    await disableButton.trigger('click')
    await flushPromises()

    expect(confirmMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已停用')
  })
})
