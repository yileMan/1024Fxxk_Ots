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
    expect(wrapper.get('button[data-action="preview-matches"]').text()).toContain('预览内部匹配')
  })

  it('previews and executes internal matching with candidate evidence', async () => {
    const taskGeneration = {
      schema_version: '1.0', status: 'pending', task_inserted_count: 2,
      task_reassess_count: 0, task_updated_count: 0, task_unchanged_count: 0,
      task_skipped_count: 1, task_failed_count: 0,
      skip_reason_counts: { PRODUCT_VERSION_DISABLED: 1 },
      task_samples: [
        { vulnerability_id: 7, cve_id: 'CVE-2026-0001', product_id: 2, product_name: '网关', product_version_id: 4, version_no: '1.0', product_ots_id: 9, owner_id: 5, action: 'inserted', reason: null },
      ],
      truncated_task_count: 0, error_code: null,
    }
    const matching = {
      schema_version: '1.0', status: 'pending', matching_rule_version: 'exact-identity-v1',
      version_rule_version: 'natural-version-v1', processed_vulnerability_count: 2,
      candidate_inserted_count: 1, candidate_updated_count: 0, candidate_removed_count: 0,
      candidate_unchanged_count: 0, unmatched_vulnerability_count: 1,
      unmatched_reason_counts: { VERSION_OUTSIDE_RANGE: 1 },
      unmatched_samples: [{ vulnerability_id: 8, cve_id: 'CVE-2026-0002', reason: 'VERSION_OUTSIDE_RANGE' }],
      truncated_unmatched_count: 0,
      candidate_samples: [{ vulnerability_id: 7, cve_id: 'CVE-2026-0001', ots_component_id: 3, ots_name: 'OpenSSL', ots_version: '3.0.0', match_method: 'cpe', match_basis: '精确版本命中', match_confidence: null, match_evidence: {} }],
      truncated_candidate_count: 0, candidate_disclaimer: '候选不等于产品受影响', error_code: null, finished_at: null,
      task_generation: taskGeneration,
    }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(response('succeeded')), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(matching), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...matching, status: 'succeeded', finished_at: '2026-08-31T00:00:00Z' }), { status: 200 }))
    window.history.replaceState({}, '', '/system/data-exchange/import-packages?batch=12')
    const wrapper = mount(ImportPackagePage)
    await flushPromises()
    await wrapper.get('button[data-action="preview-matches"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('OpenSSL 3.0.0')
    expect(wrapper.text()).toContain('VERSION_OUTSIDE_RANGE')
    expect(wrapper.text()).toContain('候选不等于产品受影响')
    expect(wrapper.text()).toContain('产品评估任务')
    expect(wrapper.text()).toContain('新任务')
    expect(wrapper.text()).toContain('网关 1.0')
    expect(wrapper.text()).toContain('PRODUCT_VERSION_DISABLED')
    expect(wrapper.text()).toContain('待产品独立评估')
    await wrapper.get('button[data-action="execute-matches"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/import-packages/12/ots-matches')
    expect(wrapper.text()).toContain('内部匹配已完成')
  })

  it('marks a legacy succeeded matching result as awaiting product task generation', async () => {
    const legacyMatching = {
      schema_version: '1.0', status: 'succeeded', matching_rule_version: 'exact-identity-v1',
      version_rule_version: 'natural-version-v1', processed_vulnerability_count: 1,
      candidate_inserted_count: 0, candidate_updated_count: 0, candidate_removed_count: 0,
      candidate_unchanged_count: 1, unmatched_vulnerability_count: 0,
      unmatched_reason_counts: {}, unmatched_samples: [], truncated_unmatched_count: 0,
      candidate_samples: [], truncated_candidate_count: 0,
      candidate_disclaimer: '候选不等于产品受影响', error_code: null, finished_at: '2026-08-31T00:00:00Z',
    }
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(response('succeeded')), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(legacyMatching), { status: 200 }))
    window.history.replaceState({}, '', '/system/data-exchange/import-packages?batch=12')
    const wrapper = mount(ImportPackagePage)
    await flushPromises()
    await wrapper.get('button[data-action="preview-matches"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('产品任务待生成')
    expect(wrapper.find('button[data-action="execute-matches"]').exists()).toBe(true)
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
