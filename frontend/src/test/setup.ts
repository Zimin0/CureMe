import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './server'

// В браузере fetch('/api/...') берёт адрес страницы, а в Node относительный URL — ошибка.
const realFetch = globalThis.fetch
globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
  realFetch(typeof input === 'string' && input.startsWith('/') ? new URL(input, location.origin) : input, init)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())
