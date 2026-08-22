import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ImportPackageApiError,
  confirmImportPackage,
  downloadPackageErrors,
  getImportPackage,
  validateImportPackage,
} from './importPackages'


const fetchMock = vi.fn()
const NativeURL = URL

const validated = {
  id: 12,
  batch_no: 'BATCH-20260822-001',
  format_version: '1.0',
  package_file_name: 'ots_intelligence_20260822_010203.zip',
  package_sha256: 'a'.repeat(64),
  status: 'validated',
  source_name: 'nvd',
  source_release: 'fkie-cad/nvd-json-data-feeds@2026-08-22',
  window_start: '2026-08-21T00:00:00+00:00',
  window_end: '2026-08-22T00:00:00+00:00',
  classification_basis: 'vulnerability_current_facts_v1',
  final_import_diff: false,
  can_import: true,
  internal_matching_pending: false,
  summary: { total: 1, new: 1, update: 0, duplicate: 0, conflict: 0, error: 0 },
  file_stats: {},
  errors: [],
  total_error_count: 0,
  truncated_error_count: 0,
  duplicate: false,
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', Object.assign(NativeURL, {
    createObjectURL: vi.fn(() => 'blob:package-errors'),
    revokeObjectURL: vi.fn(),
  }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

describe('import package API client', () => {
  it('uploads one ZIP using the generated response contract', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(validated), { status: 201 }))
    const file = new File(['package'], 'ots_intelligence_20260822_010203.zip', { type: 'application/zip' })

    await expect(validateImportPackage(file)).resolves.toEqual(validated)
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/import-packages/validate')
    expect(options.credentials).toBe('include')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    expect((options.body as FormData).get('file')).toBe(file)
  })

  it('reads an existing validation result', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(validated), { status: 200 }))

    await expect(getImportPackage(12)).resolves.toEqual(validated)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/import-packages/12', { credentials: 'include' })
  })

  it('confirms a validated batch using the generated contract', async () => {
    const succeeded = { ...validated, status: 'succeeded', can_import: false, final_import_diff: true, internal_matching_pending: true }
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(succeeded), { status: 200 }))

    await expect(confirmImportPackage(12)).resolves.toEqual(succeeded)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/import-packages/12/confirm', {
      method: 'POST', credentials: 'include',
    })
  })

  it('downloads the stable error filename', async () => {
    fetchMock.mockResolvedValueOnce(new Response('error_code,file_name\r\n', {
      status: 200,
      headers: { 'content-disposition': 'attachment; filename="package_validation_errors.csv"' },
    }))

    await expect(downloadPackageErrors(12)).resolves.toBe('package_validation_errors.csv')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:package-errors')
  })

  it('keeps stable API errors and does not create a download', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'PACKAGE_SCOPE_INVALID' }), { status: 422 }))

    await expect(validateImportPackage(new File(['x'], 'bad.zip')))
      .rejects.toEqual(expect.objectContaining<Partial<ImportPackageApiError>>({
        code: 'PACKAGE_SCOPE_INVALID',
        status: 422,
      }))
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
