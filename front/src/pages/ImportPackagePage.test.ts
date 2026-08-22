import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportPackagePage from './ImportPackagePage.vue'


const fetchMock = vi.fn()

function response(status: 'validated' | 'failed') {
  return {
    id: 12,
    batch_no: 'BATCH-20260822-001',
    format_version: '1.0',
    package_file_name: 'ots_intelligence_20260822_010203.zip',
    package_sha256: 'a'.repeat(64),
    status,
    scope_export_id: '2ef57421-4978-47b2-897c-3b8dfe7e1ea0',
    scope_count: 1,
    classification_basis: 'package_structure_v1',
    final_import_diff: false,
    can_import: false,
    summary: status === 'validated'
      ? { total: 7, new: 6, update: 0, duplicate: 1, conflict: 0, error: 0 }
      : { total: 7, new: 5, update: 0, duplicate: 0, conflict: 0, error: 2 },
    file_stats: {
      'vulnerabilities.csv': {
        total: 1, new: status === 'validated' ? 1 : 0, update: 0, duplicate: 0,
        conflict: 0, error: status === 'validated' ? 0 : 1,
        samples: status === 'validated' ? [{ cve_id: 'CVE-2026-0001', status: 'published' }] : [],
      },
    },
    errors: status === 'failed' ? [{
      error_code: 'PACKAGE_SCOPE_INVALID',
      file_name: 'matches.csv',
      row_number: 2,
      field: 'ots_id',
      reason: '候选匹配引用范围外 OTS',
      rejected_value: '999',
    }] : [],
    total_error_count: status === 'failed' ? 2 : 0,
    truncated_error_count: status === 'failed' ? 1 : 0,
    duplicate: false,
  }
}

async function chooseFile(wrapper: ReturnType<typeof mount>, name = 'ots_intelligence_20260822_010203.zip') {
  const input = wrapper.get('input[type="file"]')
  const file = new File(['package'], name, { type: 'application/zip' })
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  return file
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:package-errors'),
    revokeObjectURL: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

describe('ImportPackagePage', () => {
  it('shows the four-step gate with only upload and validation enabled', () => {
    const wrapper = mount(ImportPackagePage)
    expect(wrapper.get('h1').text()).toBe('数据包导入')
    expect(wrapper.text()).toContain('上传数据包')
    expect(wrapper.text()).toContain('校验预览')
    expect(wrapper.text()).toContain('确认导入')
    expect(wrapper.text()).toContain('查看结果')
    expect(wrapper.get('[data-step="confirm"]').attributes('aria-disabled')).toBe('true')
    expect(wrapper.get('[data-step="result"]').attributes('aria-disabled')).toBe('true')
  })

  it('uploads a ZIP then presents read-only validation evidence', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response('validated')), { status: 201 }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('校验通过，尚未正式写入')
    expect(wrapper.text()).toContain('BATCH-20260822-001')
    expect(wrapper.text()).toContain('新增')
    expect(wrapper.text()).toContain('6')
    expect(wrapper.text()).toContain('重复')
    expect(wrapper.text()).toContain('1')
    expect(wrapper.text()).toContain('vulnerabilities.csv')
    expect(wrapper.text()).toContain('CVE-2026-0001')
    expect(wrapper.get('[data-step="confirm"]').attributes('aria-disabled')).toBe('true')
  })

  it('clears stale evidence before a failed new upload', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(response('validated')), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'INTERNAL_ERROR' }), { status: 500 }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('BATCH-20260822-001')

    await chooseFile(wrapper, 'ots_intelligence_20260822_020304.zip')
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('上传或校验失败')
    expect(wrapper.text()).not.toContain('BATCH-20260822-001')
  })

  it('shows precise failed validation errors and downloads the bounded list', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(response('failed')), { status: 201 }))
      .mockResolvedValueOnce(new Response('error_code,file_name\r\n', {
        status: 200,
        headers: { 'content-disposition': 'attachment; filename="package_validation_errors.csv"' },
      }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('校验未通过')
    expect(wrapper.text()).toContain('matches.csv')
    expect(wrapper.text()).toContain('第 2 行')
    expect(wrapper.text()).toContain('ots_id')
    expect(wrapper.text()).toContain('另有 1 项未在页面展示')
    await wrapper.get('button[data-action="download-errors"]').trigger('click')
    await flushPromises()
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('rejects a non-ZIP or oversized file before upload', async () => {
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper, 'collector_scope.csv')
    expect(wrapper.get('[role="alert"]').text()).toContain('仅支持 ZIP')
    expect(wrapper.get('button[data-action="validate"]').attributes()).toHaveProperty('disabled')

    const input = wrapper.get('input[type="file"]')
    const oversized = new File([new Uint8Array(50 * 1024 * 1024 + 1)], 'ots_intelligence_20260822_010203.zip')
    Object.defineProperty(input.element, 'files', { value: [oversized], configurable: true })
    await input.trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('不能超过 50 MiB')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
