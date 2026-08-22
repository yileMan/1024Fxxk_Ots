import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportPackagePage from './ImportPackagePage.vue'


const fetchMock = vi.fn()
const NativeURL = URL

function response(status: 'validated' | 'failed' | 'succeeded') {
  const valid = status !== 'failed'
  return {
    id: 12,
    batch_no: 'BATCH-20260822-001',
    format_version: '1.0',
    package_file_name: 'ots_intelligence_20260822_010203.zip',
    package_sha256: 'a'.repeat(64),
    status,
    source_name: 'nvd',
    source_release: 'fkie-cad/nvd-json-data-feeds@2026-08-22',
    window_start: '2026-08-21T00:00:00+00:00',
    window_end: '2026-08-22T00:00:00+00:00',
    classification_basis: 'vulnerability_current_facts_v1',
    final_import_diff: status === 'succeeded',
    can_import: status === 'validated',
    internal_matching_pending: status === 'succeeded',
    summary: valid
      ? { total: 2, new: 1, update: 0, duplicate: 1, conflict: 0, error: 0 }
      : { total: 1, new: 0, update: 0, duplicate: 0, conflict: 0, error: 1 },
    file_stats: {
      'nvd_cves.csv': {
        total: valid ? 2 : 1, new: valid ? 1 : 0, update: 0, duplicate: valid ? 1 : 0,
        conflict: 0, error: valid ? 0 : 1,
        samples: valid ? [{
          cve_id: 'CVE-2026-0001', vuln_status: 'Analyzed', description: '测试漏洞',
          affected_software_json: [{ vendor: 'openssl', product: 'openssl', version: '3.0.0' }],
          cvss31_score: 7.5, cvss31_severity: 'HIGH',
        }] : [],
      },
    },
    errors: status === 'failed' ? [{
      error_code: 'PACKAGE_CSV_INVALID', file_name: 'nvd_cves.csv', row_number: 2,
      field: 'cvss_json', reason: '字段必须是标准 JSON 数组', rejected_value: '{',
    }] : [],
    total_error_count: status === 'failed' ? 1 : 0,
    truncated_error_count: 0,
    duplicate: false,
  }
}

async function chooseFile(wrapper: ReturnType<typeof mount>, name = 'ots_intelligence_20260822_010203.zip') {
  const input = wrapper.get('input[type="file"]')
  const file = new File(['package'], name, { type: 'application/zip' })
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

beforeEach(() => {
  window.history.replaceState({}, '', '/system/data-exchange/import-packages')
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', Object.assign(NativeURL, {
    createObjectURL: vi.fn(() => 'blob:package-errors'),
    revokeObjectURL: vi.fn(),
  }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('ImportPackagePage', () => {
  it('describes the two-file NVD fact boundary', () => {
    const wrapper = mount(ImportPackagePage)
    expect(wrapper.text()).toContain('固定两文件根目录')
    expect(wrapper.text()).toContain('一行一个 CVE')
    expect(wrapper.text()).toContain('不包含内部 OTS ID')
  })

  it('shows source facts and enables confirmation after validation', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response('validated')), { status: 201 }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('校验通过，可以导入漏洞事实')
    expect(wrapper.text()).toContain('fkie-cad/nvd-json-data-feeds@2026-08-22')
    expect(wrapper.text()).toContain('CVE-2026-0001')
    expect(wrapper.text()).toContain('openssl 3.0.0')
    expect(wrapper.text()).toContain('7.5 HIGH')
    expect(wrapper.get('[data-step="confirm"]').attributes('aria-disabled')).toBeUndefined()
    expect(wrapper.get('button[data-action="confirm"]').attributes('disabled')).toBeUndefined()
  })

  it('requires secondary confirmation then displays succeeded result and pending matching', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(response('validated')), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(response('succeeded')), { status: 200 }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[data-action="confirm"]').trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/import-packages/12/confirm')
    expect(wrapper.text()).toContain('漏洞事实已成功导入')
    expect(wrapper.text()).toContain('内部 OTS 匹配尚未执行')
    expect(wrapper.get('[data-step="result"]').classes()).toContain('active')
  })

  it('does not confirm when the user cancels the secondary confirmation', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response('validated')), { status: 201 }))
    vi.mocked(window.confirm).mockReturnValue(false)
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[data-action="confirm"]').trigger('click')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('shows precise failed validation errors and keeps confirmation disabled', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response('failed')), { status: 201 }))
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper)
    await wrapper.get('button[data-action="validate"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('校验未通过')
    expect(wrapper.text()).toContain('cvss_json')
    expect(wrapper.find('button[data-action="confirm"]').exists()).toBe(false)
  })

  it('rejects a non-ZIP before upload', async () => {
    const wrapper = mount(ImportPackagePage)
    await chooseFile(wrapper, 'nvd_cves.csv')
    expect(wrapper.get('[role="alert"]').text()).toContain('仅支持 ZIP')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
