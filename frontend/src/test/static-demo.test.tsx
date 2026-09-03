import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import sample from '../../../app/fixtures/demo.json'

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('VITE_STATIC_DEMO', 'true')
  // Static mode wins even over a mistakenly enabled live flag.
  vi.stubEnv('VITE_ENABLE_LIVE_SEARCH', 'true')
})
afterEach(() => {
  vi.stubEnv('VITE_STATIC_DEMO', 'false')
  vi.stubEnv('VITE_ENABLE_LIVE_SEARCH', 'false')
  vi.resetModules()
})

it('loads canonical data without any fetch and returns an independent copy', async () => {
  const api = await import('../api')
  expect(api.LIVE_ENABLED).toBe(false)
  const result = await api.loadDemo(new AbortController().signal)
  expect(result).toEqual(sample)
  expect(result).not.toBe(sample)
  expect(fetch).not.toHaveBeenCalled()
  expect(() => api.runLive('Synthetic', new File([], 'synthetic.docx'), new AbortController().signal)).toThrow('unavailable')
  expect(fetch).not.toHaveBeenCalled()
})

it('shows synthetic results without upload or live controls, including a live prop override', async () => {
  const { default: App } = await import('../App')
  const { container } = render(<App liveEnabled />)
  expect(container.querySelector('input[type="file"]')).toBeNull()
  expect(screen.queryByRole('button', { name: /Run Live Analysis/ })).not.toBeInTheDocument()
  expect(screen.getByText('Explore a synthetic replay showing how the agent turns résumé evidence and search criteria into a ranked shortlist.')).toBeInTheDocument()
  expect(screen.getByText(/Interactive replay of a completed synthetic agent run/)).toBeInTheDocument()
  expect(screen.getByText(/No providers run in this public replay/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /View source code on GitHub/ })).toHaveAttribute('href', 'https://github.com/MariaJi/ai-job-search-agent')
  expect(screen.getByText(/No resume was uploaded/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /Try Sample Demo/ }))
  expect(await screen.findByRole('heading', { name: 'Your ranked shortlist' })).toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(sample.ranked_jobs.length)
  expect(screen.getAllByText('Synthetic posting — no external source.')).toHaveLength(sample.ranked_jobs.length)
  expect(screen.queryByRole('link', { name: /Example source/ })).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})

it.each([null, {}, { ...sample, ranked_jobs: 'invalid' }, { ...sample, run_summary: null }])('rejects malformed synthetic data safely', async value => {
  const { readStaticDemo } = await import('../api')
  expect(() => readStaticDemo(value)).toThrow('The sample demo is unavailable. Please try again later.')
  expect(fetch).not.toHaveBeenCalled()
})

it('honors cancellation without making a request', async () => {
  const { loadDemo } = await import('../api')
  const controller = new AbortController()
  controller.abort()
  await expect(loadDemo(controller.signal)).rejects.toThrow()
  expect(fetch).not.toHaveBeenCalled()
})
