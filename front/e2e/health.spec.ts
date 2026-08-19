import { expect, test } from '@playwright/test'

test('健康页展示服务和数据库可用状态', async ({ page }) => {
  await page.route('**/api/v1/health', async (route) => {
    await route.fulfill({ json: { service: 'available', database: 'available' } })
  })

  await page.goto('/health')

  await expect(page.getByRole('heading', { name: '系统健康' })).toBeVisible()
  await expect(page.getByText('服务状态：可用')).toBeVisible()
  await expect(page.getByText('数据库状态：可用')).toBeVisible()
})
