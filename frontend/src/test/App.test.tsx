import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'
import JobCard from '../JobCard'
import { DOCX_TYPE, MAX_UPLOAD_BYTES, type Job, type SearchResult } from '../api'
import sample from '../../../app/fixtures/demo.json'

const fixture = () => structuredClone(sample) as SearchResult
const respond = (data: unknown = fixture(), status = 200) => vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(data), { status }))
const resume = () => new File(['synthetic DOCX boundary mock'], 'sample.docx', { type: DOCX_TYPE })

describe('safe demo workspace', () => {
  it('defaults to disabled live access, with no automatic requests', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: /run live analysis/i })).toBeDisabled()
    expect(screen.getByLabelText(/your resume/i)).toBeDisabled()
    expect(screen.getByText(/protect private data and provider costs/i)).toBeVisible()
    expect(screen.getByRole('button', { name: /try sample demo/i })).toBeEnabled()
    expect(screen.getByText(/this tool never submits applications/i)).toBeVisible()
    fireEvent.submit(screen.getByRole('button', { name: /run live analysis/i }).closest('form')!)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('loads only the sample GET, labels simulated results, and never persists data', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    respond()
    render(<App liveEnabled={false} />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    expect(await screen.findByRole('heading', { name: 'Your ranked shortlist' })).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/v1/demo', expect.objectContaining({ credentials: 'omit', cache: 'no-store' }))
    expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBeUndefined()
    expect(screen.getByText('Illustrative sample—not current openings.')).toBeVisible()
    expect(screen.getAllByText('Simulated outcome.')).toHaveLength(3)
    expect(screen.getAllByRole('article')).toHaveLength(3)
    expect(storage).not.toHaveBeenCalled()
  })

  it('renders an empty result without treating it as a failure', async () => {
    const data = fixture()
    data.ranked_jobs = []
    data.run_summary = { status: 'completed', jobs_found: 0, jobs_analyzed: 0, verification_attempted: 0, verified_jobs: 0, preliminary_jobs: 0, selected_jobs: 0, returned_jobs: 0, warnings: [] }
    respond(data)
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    expect(await screen.findByRole('heading', { name: /no matching jobs/i })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('upload and local live access', () => {
  it.each([
    [new File(['pdf'], 'resume.pdf', { type: 'application/pdf' }), /choose a DOCX file/i],
    [new File(['x'], 'resume.docx', { type: 'text/plain' }), /choose a DOCX file/i],
    [new File([], 'empty.docx', { type: DOCX_TYPE }), /file is empty/i],
    [new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], 'large.docx', { type: DOCX_TYPE }), /5 MiB or smaller/i],
  ])('rejects invalid uploads without a request (case %#)', async (file, message) => {
    render(<App liveEnabled />)
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText(/your resume/i), file)
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(fetch).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Remove file' })).not.toBeInTheDocument()
  })

  it('shows the selected file and lets the user remove it', async () => {
    render(<App liveEnabled />)
    const input = screen.getByLabelText(/your resume/i) as HTMLInputElement
    await userEvent.upload(input, resume())
    expect(screen.getByText('sample.docx')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Remove file' }))
    expect(input.files).toHaveLength(0)
    expect(screen.queryByText('sample.docx')).not.toBeInTheDocument()
  })

  it('validates both required inputs before submitting', async () => {
    render(<App liveEnabled />)
    await userEvent.click(screen.getByRole('button', { name: /run live analysis/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/choose a DOCX resume/i)
    await userEvent.upload(screen.getByLabelText(/your resume/i), resume())
    await userEvent.clear(screen.getByLabelText('What are you looking for?'))
    await userEvent.click(screen.getByRole('button', { name: /run live analysis/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/1–2000 characters/i)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('sends multipart once, shows honest loading, and clears the file afterward', async () => {
    let finish!: (response: Response) => void
    vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<App liveEnabled />)
    await userEvent.upload(screen.getByLabelText(/your resume/i), resume())
    await userEvent.click(screen.getByRole('button', { name: /run live analysis/i }))
    expect(screen.getByRole('status')).toHaveTextContent(/may take several minutes/i)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run live analysis/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /try sample demo/i })).toBeDisabled()
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/api/v1/job-search')
    expect(init?.method).toBe('POST')
    const form = init?.body as FormData
    expect([...form.keys()]).toEqual(['search_request', 'resume'])
    expect((form.get('resume') as File).name).toBe('sample.docx')
    expect(init?.headers).toBeUndefined() // Browser supplies the multipart boundary.
    await act(async () => finish(new Response(JSON.stringify(fixture()))))
    expect(await screen.findByText('Live run')).toBeVisible()
    expect(screen.queryByText('sample.docx')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('aborts the browser request on unmount without automatic retry', async () => {
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {}))
    const { unmount } = render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    expect(screen.getByRole('button', { name: /loading sample demo/i })).toBeDisabled()
    const signal = vi.mocked(fetch).mock.calls[0][1]?.signal
    unmount()
    expect(signal?.aborted).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})

describe('verification semantics', () => {
  it('shows separate preliminary and verified scores only for explicit verified analysis', () => {
    render(<JobCard job={fixture().ranked_jobs[0]} rank={1} demo={false} />)
    expect(screen.getByText('Preliminary Match Score').parentElement).toHaveTextContent('84')
    expect(screen.getByText('Verified Match Score').parentElement).toHaveTextContent('91')
    expect(screen.getByRole('link', { name: /view source/i })).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it.each([undefined, null, '', 'unknown', 'VERIFIED', 'not_needed', 'failed', '__proto__', 'constructor'])('does not label status %s as verified', status => {
    const job = { ...fixture().ranked_jobs[0], verification_status: status } as Job
    render(<JobCard job={job} rank={1} demo={false} />)
    expect(screen.queryByText('Verified Match Score')).not.toBeInTheDocument()
    expect(screen.getByText('Preliminary Match Score')).toBeVisible()
    expect(screen.getByText('No verified score available')).toBeVisible()
  })

  it('treats an explicit preliminary analysis conservatively, and rejects unsafe source links', () => {
    const job = fixture().ranked_jobs[0]
    job.analysis_type = 'preliminary'
    job.source_urls = { original: 'javascript:alert(1)', description: 'https://user:secret@example.com', verified: 'https://example.com/verified' }
    render(<JobCard job={job} rank={1} demo={false} />)
    expect(screen.queryByText('Verified Match Score')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('safe API failures', () => {
  it.each([403, 413, 422, 502, 503, 500])('sanitizes status %s instead of rendering exception data', async status => {
    respond({ error: { message: 'SECRET_PROVIDER_EXCEPTION_PRIVATE_RESUME' } }, status)
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveFocus()
    expect(alert).not.toHaveTextContent('SECRET_PROVIDER_EXCEPTION_PRIVATE_RESUME')
    expect(within(alert).getByText('We couldn’t complete that request.')).toBeVisible()
    expect(screen.getByRole('button', { name: /try sample demo/i })).toBeEnabled()
  })

  it('sanitizes network failures', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('secret in network detail'))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the API')
    expect(screen.getByRole('alert')).not.toHaveTextContent('secret in network detail')
  })

  it('rejects raw internal state and malformed responses', async () => {
    respond({ resume_text: 'PRIVATE_SENTINEL', secret: 'SECRET_SENTINEL' })
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /try sample demo/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('unsupported response')
    expect(document.body).not.toHaveTextContent('PRIVATE_SENTINEL')
    await waitFor(() => expect(screen.getByRole('button', { name: /try sample demo/i })).toBeEnabled())
  })
})
