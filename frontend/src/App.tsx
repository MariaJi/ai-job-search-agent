import { useEffect, useRef, useState, type FormEvent } from 'react'
import { STATIC_DEMO, LIVE_ENABLED, DOCX_TYPE, loadDemo, runLive, validateUpload, type SearchResult } from './api'
import JobCard from './JobCard'

export default function App({ liveEnabled: requestedLive = LIVE_ENABLED }: { liveEnabled?: boolean }) {
  const liveEnabled = !STATIC_DEMO && requestedLive
  const [search, setSearch] = useState('Find remote Senior Software Engineer and Applied AI Engineer roles in the US, posted in the last 7 days.')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<'demo' | 'live' | null>(null)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [mode, setMode] = useState<'demo' | 'live'>('demo')
  const upload = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const errorAlert = useRef<HTMLDivElement>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => { if (error) errorAlert.current?.focus() }, [error])

  function removeFile() {
    setFile(null)
    if (upload.current) upload.current.value = ''
  }
  async function run(nextMode: 'demo' | 'live') {
    if (busy || (nextMode === 'live' && !liveEnabled)) return
    if (nextMode === 'live') {
      const invalid = !search.trim() || search.trim().length > 2000 ? 'Describe your search in 1–2000 characters.'
        : !file ? 'Choose a DOCX resume before running live analysis.' : validateUpload(file)
      if (invalid) { setError(invalid); return }
    }
    const current = new AbortController()
    controller.current = current
    setBusy(nextMode)
    setError('')
    setResult(null)
    try {
      const data = nextMode === 'demo' ? await loadDemo(current.signal) : await runLive(search, file!, current.signal)
      if (!current.signal.aborted) {
        setResult(data)
        setMode(nextMode)
        requestAnimationFrame(() => resultHeading.current?.focus())
      }
    } catch (failure) {
      if (!current.signal.aborted) setError(failure instanceof Error ? failure.message : 'The request could not be completed.')
    } finally {
      if (!current.signal.aborted) {
        setBusy(null)
        if (nextMode === 'live') removeFile()
      }
    }
  }
  function submit(event: FormEvent) { event.preventDefault(); void run('live') }

  return <>
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header className="topbar"><a className="brand" href="#workspace"><span className="brand-mark" aria-hidden="true">↗</span><span>AI Job Search Agent<small>Evidence before applications</small></span></a><span className="environment">{liveEnabled ? 'Local live access enabled' : 'Demo-safe workspace'}</span></header>
    <main id="workspace" className="workspace">
      <aside className="search-panel" aria-labelledby="search-title">
        <p className="eyebrow">Your next move</p><h1 id="search-title">Find the fit.<br /><em>See the evidence.</em></h1>
        <p className="intro">Turn a resume and a search request into a ranked shortlist—with the uncertainty left visible.</p>
        <form onSubmit={submit} noValidate>
          <label htmlFor="search">What are you looking for?</label>
          <textarea id="search" rows={5} maxLength={2000} value={search} disabled={STATIC_DEMO || !!busy} onChange={e => setSearch(e.target.value)} aria-describedby="search-help" />
          <p className="field-help" id="search-help">{STATIC_DEMO ? 'Illustrative search criteria. Choose Try Sample Demo to explore the bundled results.' : 'Include a role, location, and time window. The sample uses its own illustrative criteria.'}</p>
          {!STATIC_DEMO && <><label htmlFor="resume">Your resume <span className="label-detail">DOCX · up to 5 MiB</span></label>
          <div className={`upload-box ${!liveEnabled ? 'disabled-upload' : ''}`}>
            <input ref={upload} id="resume" type="file" accept={`.docx,${DOCX_TYPE}`} disabled={!liveEnabled || !!busy} aria-describedby="resume-help" onChange={e => {
              const selected = e.target.files?.[0]
              if (!selected) return
              const invalid = validateUpload(selected)
              setError(invalid || '')
              if (invalid) removeFile(); else setFile(selected)
            }} />
            {file && <div className="selected-file"><span>{file.name}<small>{Math.ceil(file.size / 1024)} KiB · ready to upload</small></span><button type="button" className="text-button" disabled={!!busy} onClick={removeFile}>Remove file</button></div>}
            <p id="resume-help">{liveEnabled ? 'Sent only when you run live analysis. No browser storage; file selection is cleared after the request.' : 'Uploads are disabled in this public-demo configuration.'}</p>
          </div></>}
          <button className="button primary" type="button" disabled={!!busy} onClick={() => void run('demo')}>{busy === 'demo' ? 'Loading Sample Demo…' : 'Try Sample Demo'} <span aria-hidden="true">↗</span></button>
          {!STATIC_DEMO && <button className="button secondary" type="submit" disabled={!liveEnabled || !!busy}>Run Live Analysis <span aria-hidden="true">→</span></button>}
          {STATIC_DEMO && <p className="privacy-note">Synthetic sample only. No resume was uploaded. This demo runs entirely in your browser without a backend or provider calls.</p>}
          <div className="privacy-note"><strong>{liveEnabled ? 'Private, local use only' : 'Sample first. No provider costs.'}</strong><p>{liveEnabled ? 'Live analysis sends resume-derived information to external providers and may incur costs. This tool never submits applications.' : 'Live analysis is disabled in the public demo to protect private data and provider costs. No resume or API keys are needed for the sample.'}</p></div>
        </form>
        <p className="stack-note">LangGraph workflow <span> / </span> FastAPI <span> / </span> React</p>
      </aside>
      <section className="results-panel" aria-labelledby="results-title" aria-busy={!!busy}>
        <div className="section-heading"><div><p className="eyebrow">Search intelligence</p><h2 id="results-title" ref={resultHeading} tabIndex={-1}>{result ? 'Your ranked shortlist' : 'A shortlist you can inspect'}</h2></div><span className="outline-badge">{result ? mode === 'demo' ? 'Sample run' : 'Live run' : 'Ready to explore'}</span></div>
        {error && <div ref={errorAlert} tabIndex={-1} className="error-message" role="alert"><strong>We couldn’t complete that request.</strong><p>{error}</p></div>}
        {busy && <div className="loading-state" role="status"><span className="spinner" aria-hidden="true" /><h3>{busy === 'demo' ? 'Loading the sample…' : 'Analysis is running…'}</h3><p>{busy === 'demo' ? 'Reading synthetic results. No providers are being called.' : 'Analysis may take several minutes. The workflow is searching, matching, and checking sources. Keep this page open; there is no completion estimate.'}</p></div>}
        {!result && !busy && <div className="welcome-state"><span className="eyebrow">A transparent workflow</span><h3>Not just a score.<br />The reasoning behind it.</h3><p>Explore three illustrative roles to see how match evidence, skill gaps, and source verification shape a shortlist.</p><div className="workflow-notes"><div><b>01</b><span><strong>Understand the search</strong>Extract criteria and a concise candidate profile.</span></div><div><b>02</b><span><strong>Compare the evidence</strong>Rank roles with strengths and missing skills.</span></div><div><b>03</b><span><strong>Make uncertainty visible</strong>Keep preliminary matches distinct from verified analysis.</span></div></div><p className="welcome-footnote">Sample results are invented for demonstration, not live job openings.</p></div>}
        {result && <>
          {mode === 'demo' && <div className="demo-notice"><strong>Illustrative sample—not current openings.</strong> Companies, candidate profile, scores, and verification outcomes are synthetic. No resume was uploaded or providers called.</div>}
          <dl className="metrics"><div><dt>Jobs found</dt><dd>{result.run_summary.jobs_found}</dd></div><div><dt>Analyzed</dt><dd>{result.run_summary.jobs_analyzed}</dd></div><div><dt>Verified</dt><dd>{result.run_summary.verified_jobs}</dd></div><div><dt>Preliminary</dt><dd>{result.run_summary.preliminary_jobs}</dd></div></dl>
          <details className="run-details"><summary>Search criteria & candidate summary</summary><p>{result.criteria.role} · {result.criteria.location} · {result.criteria.employment_type} · Last {result.criteria.days_old} days</p><p>{result.candidate_profile.summary}</p><p>{result.run_summary.verification_attempted} verification attempts · {result.run_summary.selected_jobs} selected · {result.run_summary.returned_jobs} returned · Run {result.run_summary.status}</p></details>
          {result.run_summary.warnings.length > 0 && <div className="run-warnings" role="status">{result.run_summary.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</div>}
          {result.ranked_jobs.length === 0 ? <div className="empty-state"><h3>No matching jobs this time.</h3><p>Try a broader role, location, or date window. An empty shortlist is a valid completed result.</p></div> : <div className="job-list">{result.ranked_jobs.map((job, i) => <JobCard key={i} job={job} rank={i + 1} demo={mode === 'demo'} />)}</div>}
        </>}
        <footer className="results-footer">Decision support, not a hiring prediction. This tool never submits applications. Review the original posting before applying.</footer>
      </section>
    </main>
  </>
}
