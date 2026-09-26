import { render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import JobCard from '../JobCard'
import type { Job } from '../api'
import sample from '../../../app/fixtures/demo.json'

const statuses: unknown[] = ['source_not_found', 'not_found', 'not_attempted', 'not_needed',
  'unverified', 'pending', 'failed', 'service_error', 'unknown', '', undefined, null,
  true, 1, [], {}, 'VERIFIED', ' verified ', '__proto__', 'constructor']

it.each(statuses.flatMap(status => ['verified', 'preliminary'].flatMap(analysis =>
  ['Apply', 'Strong Apply'].map(recommendation => ({ status, analysis, recommendation })))))(
  'requires review for status $status, analysis $analysis and $recommendation',
  ({ status, analysis, recommendation }) => {
    const job = { ...sample.ranked_jobs[0], verification_status: status,
      analysis_type: analysis, recommendation } as Job
    render(<JobCard job={job} rank={1} demo={false} />)
    const footer = screen.getByText('Recommendation').closest('footer')!
    expect(within(footer).getByText('Review original posting')).toBeVisible()
    expect(within(footer).queryByText(/^(Strong )?Apply$/)).not.toBeInTheDocument()
  })

it.each([
  ['Strong Apply', 'Apply'], ['Apply', 'Apply'], ['Maybe', 'Maybe'], ['Skip', 'Skip'],
  ['Definitely Apply now', 'Review original posting'], ['', 'Review original posting'],
])('maps verified recommendation %s to %s', (recommendation, expected) => {
  const job = { ...sample.ranked_jobs[0], verification_status: 'verified',
    analysis_type: 'verified', recommendation } as Job
  render(<JobCard job={job} rank={1} demo={false} />)
  const footer = screen.getByText('Recommendation').closest('footer')!
  expect(within(footer).getByText(expected)).toBeVisible()
})

it('does not promote explicitly preliminary analysis with a verified source', () => {
  const job = { ...sample.ranked_jobs[0], verification_status: 'verified',
    analysis_type: 'preliminary', recommendation: 'Apply' } as Job
  render(<JobCard job={job} rank={1} demo={false} />)
  expect(screen.getByText('Review original posting')).toBeVisible()
})

it.each(['verified', 'failed', 'not_attempted'])(
  'labels source links accurately for %s jobs without promoting recommendations', status => {
    const job = { ...sample.ranked_jobs[0], verification_status: status,
      analysis_type: status === 'verified' ? 'verified' : 'preliminary', recommendation: 'Apply',
      source_urls: { original: 'https://jooble.org/desc/example',
        verified: 'https://example.com/careers/1', description: null } } as Job
    render(<JobCard job={job} rank={1} demo={false} />)
    expect(screen.getByRole('link', { name: /^Review source/ })).toHaveAttribute('href', job.source_urls.original)
    if (status === 'verified') {
      expect(screen.getByRole('link', { name: /^View verified source/ })).toHaveAttribute('href', job.source_urls.verified)
      expect(screen.getByText('Apply')).toBeVisible()
    } else {
      expect(screen.queryByRole('link', { name: /^View verified source/ })).not.toBeInTheDocument()
      expect(screen.getByText('Review original posting')).toBeVisible()
      expect(screen.queryByText('Apply')).not.toBeInTheDocument()
    }
  })

it('does not label a fallback original URL as verified', () => {
  const job = { ...sample.ranked_jobs[0], verification_status: 'verified', analysis_type: 'verified',
    source_urls: { original: 'https://jooble.org/desc/example', verified: null, description: null } } as Job
  render(<JobCard job={job} rank={1} demo={false} />)
  expect(screen.getByRole('link', { name: /^Review source/ })).toHaveAttribute('href', job.source_urls.original)
  expect(screen.queryByRole('link', { name: /^View verified source/ })).not.toBeInTheDocument()
})
