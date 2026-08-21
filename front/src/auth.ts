import { reactive } from 'vue'

import { currentUser, type PublicUser } from './api/auth'
import { currentScopeSummary, type ProductScopeSummary } from './api/scopes'

export const authentication = reactive<{
  user: PublicUser | null
  initialized: boolean
  scope: ProductScopeSummary | null
  scopeInitialized: boolean
  feedback: string
}>({ user: null, initialized: false, scope: null, scopeInitialized: false, feedback: '' })

let initialization: Promise<PublicUser | null> | null = null

function setSessionFailure(): void {
  authentication.user = null
  authentication.scope = null
  authentication.scopeInitialized = true
  authentication.feedback = ''
}

async function restoreScope(): Promise<void> {
  if (authentication.scopeInitialized || !authentication.user) return
  if (authentication.user.roles.includes('admin')) {
    authentication.scope = {
      is_global: true,
      scopes: [],
      effective_product_ids: [],
      effective_version_ids: [],
    }
    authentication.scopeInitialized = true
    return
  }
  try {
    authentication.scope = await currentScopeSummary()
  } catch {
    authentication.scope = null
    authentication.feedback = '产品授权状态暂时不可用，请刷新页面重试'
  } finally {
    authentication.scopeInitialized = true
  }
}

export async function restoreAuthentication(): Promise<PublicUser | null> {
  if (authentication.initialized) {
    await restoreScope()
    return authentication.user
  }
  initialization ??= currentUser()
    .then(async (user) => {
      authentication.user = user
      authentication.feedback = ''
      await restoreScope()
      return user
    })
    .catch(() => {
      setSessionFailure()
      return null
    })
    .finally(() => {
      authentication.initialized = true
      initialization = null
    })
  return initialization
}

export function setAuthenticatedUser(user: PublicUser): void {
  authentication.user = user
  authentication.initialized = true
  authentication.scope = null
  authentication.scopeInitialized = false
  authentication.feedback = ''
}

export function clearAuthenticatedUser(): void {
  authentication.user = null
  authentication.initialized = true
  authentication.scope = null
  authentication.scopeInitialized = true
  authentication.feedback = ''
}

export function resetAuthenticationForTesting(): void {
  authentication.user = null
  authentication.initialized = false
  authentication.scope = null
  authentication.scopeInitialized = false
  authentication.feedback = ''
  initialization = null
}
