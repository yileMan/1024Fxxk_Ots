import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ImportPackageApiError,
  downloadPackageErrors,
  getImportPackage,
  validateImportPackage,
} from './importPackages'


const fetchMock = vi.fn()

const validated = {
  id: 12,
  batch_no: 'BATCH-20260822-001',
  format_version: '1.0',
  package_file_name: 'ots_intelligence_20260822_010203.zip',
  package_sha256: 'a'.repeat(64),
  status: 'validated',
  scope_export_id: '2ef57421-4978-47b2-897c-3b8dfe7e1ea0',
  scope_count: 1,
  classification_basis: 'package_structure_v1',
  final_import_diff: false,
  can_import: false,
  summary: { total: 7, new: 7, update: 0, duplicate: 0, conflict: 0, error: 0 },
  file_stats: {},
  errors: [],
  total_error_count: 0,
  truncated_error_count: 0,
  duplicate: false,
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

    await expect(validateImportPackage(new File(['x'], 'bad.zip'))
      .rejects.toEqual(expect.objectContaining<Partial<ImportPackageApiError>>({
        code: 'PACKAGE_SCOPE_INVALID',
        status: 422,
      })))
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
