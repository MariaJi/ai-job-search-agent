import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Keep tests independent of a developer's local live-mode configuration.
vi.stubEnv('VITE_ENABLE_LIVE_SEARCH', 'false')
vi.stubEnv('VITE_STATIC_DEMO', 'false')
vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000')

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network access is forbidden in tests')))
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
