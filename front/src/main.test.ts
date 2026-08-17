import { beforeEach, expect, it, vi } from 'vitest'

beforeEach(() => {
  document.body.innerHTML = '<div id="app"></div>'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'AUTH_SESSION_INVALID' }), { status: 401 })),
  )
  vi.resetModules()
})

it('mounts the authenticated application shell', async () => {
  await import('./main')

  expect(document.querySelector('#app')?.textContent).toContain('OTS 信息维护平台')
})
