import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
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

it('shows disabled private capabilities and synthetic results, including a live prop override', async () => {
  const api = await import('../api')
  const live = vi.spyOn(api, 'runLive')
  const { default: App } = await import('../App')
  render(<App liveEnabled />)
  const resume = screen.getByLabelText(/Your resume/) as HTMLInputElement
  const liveButton = screen.getByRole('button', { name: /Run Live Analysis.*Private mode only/ })
  expect(resume).toBeVisible()
  expect(resume).toBeDisabled()
  expect(liveButton).toBeVisible()
  expect(liveButton).toBeDisabled()
  expect(screen.getByRole('button', { name: /Try Sample Demo/ })).toBeEnabled()
  expect(screen.getByText('Private mode only · DOCX')).toBeVisible()
  expect(screen.getByText('Resume upload is available in private mode.')).toBeVisible()
  expect(within(liveButton).getByText('Private mode only').tagName).toBe('SMALL')
  expect(screen.getByText(/Resume upload and live analysis are private-only/)).toBeVisible()
  await userEvent.upload(resume, new File(['synthetic'], 'resume.docx', { type: api.DOCX_TYPE }))
  expect(resume.files).toHaveLength(0)
  await userEvent.click(liveButton)
  fireEvent.submit(liveButton.closest('form')!)
  expect(live).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText('Explore a synthetic replay showing how the agent turns résumé evidence and search criteria into a ranked shortlist.')).toBeInTheDocument()
  expect(screen.getByText(/This browser-only demo uses a synthetic candidate and bundled results, with no backend or provider calls/)).toBeVisible()
  expect(screen.getByText(/No providers run in this public replay/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /View source code on GitHub/ })).toHaveAttribute('href', 'https://github.com/MariaJi/ai-job-search-agent')
  expect(screen.getByText(/No resume is uploaded/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: /Try Sample Demo/ }))
  expect(await screen.findByRole('heading', { name: 'Your ranked shortlist' })).toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(sample.ranked_jobs.length)
  const cards = screen.getAllByRole('article')
  const guide = screen.getByRole('region', { name: 'How to read these results' })
  expect(guide).toBeVisible()
  for (const label of ['Match', 'Verified', 'Eligibility', 'Recommendation']) {
    expect(within(guide).getByText(label, { exact: true })).toBeVisible()
  }
  expect(within(guide).getByText(/84 → 91 in this sample/)).toBeVisible()
  expect(within(guide).getByText(/not eligibility or an automatic recommendation/)).toBeVisible()
  expect(within(guide).getByText(/Unknown means insufficient evidence, not confirmed eligibility/)).toBeVisible()
  expect(within(guide).getByText(/contradiction forces Skip, even for a Verified, high-scoring job/)).toBeVisible()
  expect(within(guide).getByText(/Private workflow illustrated here \(no provider calls\)/)).toBeVisible()
  expect(guide.nextElementSibling).toBe(cards[0].parentElement)
  expect(sample.criteria.employment_type).toBe('')
  await userEvent.click(screen.getByText('Search criteria & candidate summary'))
  expect(screen.getByText('Employment type: Not specified (preference only)')).toBeVisible()
  expect(screen.queryByText('Employment type: Full-time (preference only)')).not.toBeInTheDocument()
  expect(within(cards[0]).getByText(/Remote, US.*Full-time/)).toBeVisible()
  expect(within(cards[0]).getByText('Apply')).toBeInTheDocument()
  expect(within(cards[0]).getByText('Verified Match Score')).toBeInTheDocument()
  expect(within(cards[1]).getByText('Source not found')).toBeInTheDocument()
  expect(within(cards[2]).getByText('Not attempted')).toBeInTheDocument()
  for (const card of cards.slice(1)) {
    expect(within(card).getByText('Review original posting')).toBeInTheDocument()
    expect(within(card).queryByText('Apply')).not.toBeInTheDocument()
    expect(within(card).getByText('No verified score available')).toBeInTheDocument()
  }
  expect(screen.getAllByText('Synthetic posting — no external source.')).toHaveLength(sample.ranked_jobs.length)
  expect(screen.queryByRole('link', { name: /Example source/ })).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  expect(live).not.toHaveBeenCalled()
  live.mockRestore()
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
