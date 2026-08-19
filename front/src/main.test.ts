import { beforeEach, expect, it, vi } from 'vitest'

beforeEach(() => {
  document.body.innerHTML = '<div id="app"></div>'
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ id: 1, login_name: 'admin', display_name: '初始管理员', roles: ['admin'] }),
        { status: 200 },
      ),
    ),
  )
  vi.resetModules()
})

it('restores the user-id cookie identity before mounting', async () => {
  await import('./main')
  await vi.waitFor(() => expect(document.querySelector('#app')?.textContent).toContain('初始管理员'))
})
