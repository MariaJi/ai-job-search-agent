import { expect, it, vi } from 'vitest'
import sample from '../../../app/fixtures/demo.json'

it('targets a configurable demo-only HTTPS backend with live mode disabled', async () => {
  vi.resetModules()
  vi.stubEnv('VITE_API_BASE_URL', 'https://demo-backend.example/')
  vi.stubEnv('VITE_ENABLE_LIVE_SEARCH', 'false')
  try {
    const api = await import('../api')
    expect(api.LIVE_ENABLED).toBe(false)
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(sample)))
    await expect(api.loadDemo(new AbortController().signal)).resolves.toEqual(sample)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('https://demo-backend.example/api/v1/demo',
      expect.objectContaining({ credentials: 'omit', cache: 'no-store' }))
    expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBeUndefined()
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBeUndefined()
  } finally {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000')
    vi.stubEnv('VITE_ENABLE_LIVE_SEARCH', 'false')
    vi.resetModules()
  }
})
