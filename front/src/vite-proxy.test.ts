// @vitest-environment node

import { describe, expect, it } from 'vitest'

import config from '../vite.config'

describe('Vite development proxy', () => {
  it('forwards API requests to the backend service', () => {
    expect(config.server?.proxy?.['/api']).toMatchObject({
      target: 'http://localhost:5353',
      changeOrigin: true,
    })
  })
})
