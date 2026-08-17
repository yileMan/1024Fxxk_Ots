import { beforeEach, expect, it, vi } from 'vitest'


beforeEach(() => {
  document.body.innerHTML = '<div id="app"></div>'
  vi.resetModules()
})

it('mounts the application', async () => {
  await import('./main.ts')

  expect(document.querySelector('#app')?.textContent).toContain('OTS 信息维护平台')
})
