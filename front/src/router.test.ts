import { describe, expect, it } from 'vitest'

import { router } from './router'


describe('OTS-11 routes', () => {
  it('keeps catalog routes authenticated but available to scoped ordinary users', () => {
    const routes = new Map(router.getRoutes().map(route => [route.path, route]))
    for (const path of [
      '/system/assessments/tasks',
      '/system/assessments/:assessmentId',
      '/system/vulnerabilities',
      '/system/vulnerabilities/:vulnerabilityId',
    ]) {
      expect(routes.get(path)?.meta.requiresAuthentication).toBe(true)
      expect(routes.get(path)?.meta.requiresAdmin).not.toBe(true)
    }
  })

  it('preserves the legacy candidate URL without an admin-only client gate', () => {
    const legacy = router.getRoutes().find(route => route.path === '/system/vulnerabilities/:vulnerabilityId/ots-matches')
    expect(legacy).toBeDefined()
    expect(legacy?.meta.requiresAuthentication).toBe(true)
    expect(legacy?.meta.requiresAdmin).not.toBe(true)
  })
})

describe('OTS-20 routes', () => {
  it('allows authenticated scoped users to open assessment export', () => {
    const route = router.getRoutes().find(item => item.path === '/system/data-exchange/assessment-export')
    expect(route?.meta.requiresAuthentication).toBe(true)
    expect(route?.meta.requiresAdmin).not.toBe(true)
  })
})

describe('OTS-21 routes', () => {
  it('keeps audit and detailed operations pages administrator-only', () => {
    for (const path of ['/system/audit-logs', '/system/operations']) {
      const route = router.getRoutes().find(item => item.path === path)
      expect(route?.meta.requiresAuthentication).toBe(true)
      expect(route?.meta.requiresAdmin).toBe(true)
    }
  })
})
