import { reactive } from 'vue'

import { currentUser, type PublicUser } from './api/auth'

export const authentication = reactive<{
  user: PublicUser | null
  initialized: boolean
  feedback: string
}>({ user: null, initialized: false, feedback: '' })

let initialization: Promise<PublicUser | null> | null = null

function setSessionFailure(): void {
  authentication.user = null
  authentication.feedback = ''
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
  authentication.feedback = ''
}

export function clearAuthenticatedUser(): void {
  authentication.user = null
  authentication.initialized = true
  authentication.feedback = ''
}

export function resetAuthenticationForTesting(): void {
  authentication.user = null
  authentication.initialized = false
  authentication.feedback = ''
  initialization = null
}
