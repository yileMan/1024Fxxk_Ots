import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:4173', channel: process.env.PLAYWRIGHT_CHANNEL },
  webServer: {
    command: 'npm run dev -- --port 4173',
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
})
