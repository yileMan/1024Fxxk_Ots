import { beforeEach, describe, expect, it, vi } from 'vitest'

import { downloadAssessmentExport, previewAssessmentExport } from './assessmentExport'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:export'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

describe('assessment export API', () => {
  it('previews the selected range with credentials', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      product_version_id: 2, product_name: '产品 A', version_no: '1.0',
      ots_id: 3, ots_name: 'OpenSSL', ots_version: '3.0', row_count: 4,
      previewed_at: '2026-09-06T00:00:00Z',
    }), { status: 200 }))
    await expect(previewAssessmentExport(2, 3)).resolves.toEqual(expect.objectContaining({ row_count: 4 }))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/assessment-exports/preview?product_version_id=2&ots_id=3',
      { credentials: 'include' },
    )
  })

  it('does not save a JSON error as CSV', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'ASSESSMENT_EXPORT_EMPTY' }), {
      status: 409, headers: { 'content-type': 'application/json' },
    }))
    await expect(downloadAssessmentExport(2, 3)).rejects.toEqual(
      expect.objectContaining({ code: 'ASSESSMENT_EXPORT_EMPTY', status: 409 }),
    )
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})
