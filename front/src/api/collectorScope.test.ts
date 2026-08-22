import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CollectorScopeApiError, downloadCollectorScope, getCollectorScope } from './collectorScope'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:collector-scope'),
    revokeObjectURL: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
})

describe('collector scope API client', () => {
  it('reads the generated preview contract with credentials', async () => {
    const preview = {
      scope_count: 0,
      items: [],
      comparison_baseline: { available: false, batch_no: null, finished_at: null },
      changes: { added_ots_ids: [], removed_ots_ids: [], added_count: 0, removed_count: 0 },
    }
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(preview), { status: 200 }))

    await expect(getCollectorScope()).resolves.toEqual(preview)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/collector-scope', { credentials: 'include' })
  })

  it('downloads the response filename and returns export evidence', async () => {
    fetchMock.mockResolvedValueOnce(new Response('scope_export_id,ots_id\r\n', {
      status: 200,
      headers: {
        'content-disposition': 'attachment; filename="collector_scope.csv"',
        'x-scope-export-id': '9aa5f26f-7f89-4653-8e2e-9c995e849d63',
        'x-content-sha256': 'a'.repeat(64),
      },
    }))

    await expect(downloadCollectorScope()).resolves.toEqual({
      fileName: 'collector_scope.csv',
      scopeExportId: '9aa5f26f-7f89-4653-8e2e-9c995e849d63',
      sha256: 'a'.repeat(64),
    })
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:collector-scope')
  })

  it('keeps structured API errors and never creates a file on failure', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'COLLECTOR_SCOPE_HISTORY_INVALID' }), { status: 500 }))

    await expect(downloadCollectorScope()).rejects.toEqual(
      expect.objectContaining<Partial<CollectorScopeApiError>>({
        code: 'COLLECTOR_SCOPE_HISTORY_INVALID',
        status: 500,
      }),
    )
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})

