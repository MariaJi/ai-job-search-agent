import sample from '../../app/fixtures/demo.json'

export interface Job {
  title: string
  company: string
  location: string
  employment_type: string | null
  verification_status?: string | null
  analysis_type: 'preliminary' | 'verified'
  preliminary_match_score: number | null
  verified_match_score: number | null
  confidence: string
  strengths: string[]
  missing_skills: string[]
  recommendation: string
  source_urls: { original: string | null; verified: string | null; description: string | null }
}

export interface SearchResult {
  criteria: { role: string; location: string; employment_type: string; days_old: number }
  candidate_profile: { summary: string; years_experience: number | null }
  ranked_jobs: Job[]
  run_summary: {
    status: 'completed' | 'partial'
    jobs_found: number; jobs_analyzed: number; verification_attempted: number
    verified_jobs: number; preliminary_jobs: number; selected_jobs: number; returned_jobs: number
    warnings: string[]
  }
}

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
export const DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
export const STATIC_DEMO = import.meta.env.VITE_STATIC_DEMO === 'true'
export const LIVE_ENABLED = !STATIC_DEMO && import.meta.env.VITE_ENABLE_LIVE_SEARCH === 'true'
const API_BASE = STATIC_DEMO ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export function validateUpload(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.docx') || !['', DOCX_TYPE, 'application/octet-stream'].includes(file.type)) {
    return 'Choose a DOCX file. PDF and older DOC files are not supported.'
  }
  if (file.size === 0) return 'This file is empty. Choose a readable DOCX resume.'
  if (file.size > MAX_UPLOAD_BYTES) return 'Your resume must be 5 MiB or smaller.'
  return null
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(v => typeof v === 'string')
const nullableString = (v: unknown) => v === null || typeof v === 'string'
const score = (v: unknown) => v === null || (Number.isInteger(v) && Number(v) >= 0 && Number(v) <= 100)
const count = (v: unknown) => Number.isInteger(v) && Number(v) >= 0
const sourceURLs = (v: unknown) => record(v) && ['original', 'verified', 'description'].every(k => nullableString(v[k]))

// Validate the public boundary; never render an error body or arbitrary graph state.
function validResult(value: unknown): value is SearchResult {
  if (!record(value) || !record(value.criteria) || !record(value.candidate_profile) || !record(value.run_summary)) return false
  const { criteria: c, candidate_profile: p, run_summary: r } = value
  return ['role', 'location', 'employment_type'].every(k => typeof c[k] === 'string') && count(c.days_old)
    && typeof p.summary === 'string' && (p.years_experience === null || count(p.years_experience))
    && (r.status === 'completed' || r.status === 'partial') && strings(r.warnings)
    && ['jobs_found', 'jobs_analyzed', 'verification_attempted', 'verified_jobs', 'preliminary_jobs', 'selected_jobs', 'returned_jobs'].every(k => count(r[k]))
    && Array.isArray(value.ranked_jobs) && value.ranked_jobs.every(j => record(j)
      && ['title', 'company', 'location', 'confidence', 'recommendation'].every(k => typeof j[k] === 'string')
      && nullableString(j.employment_type)
      // Unknown/missing status is deliberately accepted and rendered unverified.
      && (j.verification_status === undefined || nullableString(j.verification_status))
      && (j.analysis_type === 'preliminary' || j.analysis_type === 'verified')
      && score(j.preliminary_match_score) && score(j.verified_match_score)
      && strings(j.strengths) && strings(j.missing_skills)
      && sourceURLs(j.source_urls))
}

const errors: Record<number, string> = {
  400: 'The upload could not be processed. Check your file and try again.',
  403: 'Live analysis is disabled on the server. Try the sample demo.',
  413: 'The upload is too large. Choose a DOCX resume of 5 MiB or smaller.',
  415: 'Choose a DOCX resume, not a PDF or older DOC file.',
  422: 'Check your search request and upload a readable DOCX with body or table text.',
  502: 'A search provider is unavailable. Please try again later.',
  503: 'Live analysis is not configured on this server. Try the sample demo.',
}

async function request(path: string, options: RequestInit): Promise<SearchResult> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, credentials: 'omit', cache: 'no-store' })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    // eslint-disable-next-line preserve-caught-error -- Discard untrusted details at the public UI boundary.
    throw new Error('Cannot reach the API. Check that the local service is running and its CORS origin is configured.')
  }
  if (!response.ok) throw new Error(errors[response.status] || 'The request could not be completed. Please try again later.')
  let body: unknown
  try { body = await response.json() } catch { throw new Error('The API returned an unreadable response. Please try again later.') }
  if (!validResult(body)) throw new Error('The API returned an unsupported response. Please check the service version.')
  return body
}

export function readStaticDemo(value: unknown): SearchResult {
  if (!validResult(value)) throw new Error('The sample demo is unavailable. Please try again later.')
  return structuredClone(value)
}

export async function loadDemo(signal: AbortSignal): Promise<SearchResult> {
  if (STATIC_DEMO) {
    signal.throwIfAborted()
    return readStaticDemo(sample)
  }
  return request('/api/v1/demo', { signal })
}
export function runLive(search: string, resume: File, signal: AbortSignal) {
  if (STATIC_DEMO) throw new Error('Live analysis is unavailable in the static demo.')
  const form = new FormData()
  form.append('search_request', search.trim())
  form.append('resume', resume)
  return request('/api/v1/job-search', { method: 'POST', body: form, signal })
}

export function sourceLink(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch { return null }
}
