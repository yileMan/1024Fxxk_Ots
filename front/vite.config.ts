import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: 'localhost',
    proxy: {
      '/api': {
        target: 'http://localhost:5353',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    exclude: ['**/node_modules/**', 'e2e/**'],
    coverage: {
      reporter: ['text'],
      exclude: ['dist/**', 'e2e/**', 'node_modules/**', 'playwright.config.ts', 'src/env.d.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        statements: 80,
      },
    },
  },
})
