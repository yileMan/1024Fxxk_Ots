import { reactive } from 'vue'

import { AuthenticationError, currentUser, type PublicUser } from './api/auth'

export const authentication = reactive<{
  user: PublicUser | null
  initialized: boolean
  feedback: string
}>({ user: null, initialized: false, feedback: '' })

let initialization: Promise<PublicUser | null> | null = null

function setSessionFailure(code: string): void {
  authentication.user = null
  authentication.feedback = code === 'AUTH_USER_DISABLED' ? '账号已停用' : '会话已失效'
}

export async function restoreAuthentication(): Promise<PublicUser | null> {
  if (authentication.initialized) {
    return authentication.user
  }
  initialization ??= currentUser()
    .then((user) => {
      authentication.user = user
      authentication.feedback = ''
      return user
    })
    .catch((error: unknown) => {
      setSessionFailure(error instanceof AuthenticationError ? error.code : 'NETWORK_ERROR')
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
  authentication.feedback = ''
}

export function clearAuthentication(message = ''): void {
  authentication.user = null
  authentication.initialized = true
  authentication.feedback = message
}

export function resetAuthenticationForTesting(): void {
  authentication.user = null
  authentication.initialized = false
  authentication.feedback = ''
  initialization = null
}
