import { beforeEach, expect, it, vi } from 'vitest'


beforeEach(() => {
  document.body.innerHTML = '<div id="app"></div>'
  vi.resetModules()
})

it('mounts the application', async () => {
  await import('./main.js')

  expect(document.querySelector('#app')?.textContent).toBe('fuck 1024')
})
