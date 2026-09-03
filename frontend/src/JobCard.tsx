import { sourceLink, type Job } from './api'

const explanations: Record<string, [string, string]> = {
  verified: ['Verified', 'The workflow found a source and completed verified analysis. This is not a hiring guarantee.'],
  not_needed: ['Full description available', 'Verification was skipped because a complete description was available. The score is still preliminary.'],
  not_attempted: ['Not attempted', 'This role was not selected for verification. Treat its match score as preliminary.'],
  pending: ['Pending verification', 'Verification is not complete. Only a preliminary score is available.'],
  not_found: ['Source not found', 'A source could not be confirmed. Preliminary results are preserved.'],
  failed: ['Verification failed', 'Verification did not complete successfully. Preliminary results are preserved.'],
  service_error: ['Provider unavailable', 'A verification service was unavailable. Preliminary results are preserved.'],
}

export default function JobCard({ job, rank, demo }: { job: Job; rank: number; demo: boolean }) {
  const verified = job.verification_status === 'verified' && job.analysis_type === 'verified'
  const status = typeof job.verification_status === 'string' ? job.verification_status : 'unverified'
  const recommendation = verified && ['Apply', 'Strong Apply'].includes(job.recommendation)
    ? 'Apply' : verified && ['Maybe', 'Skip'].includes(job.recommendation)
      ? job.recommendation : 'Review original posting'
  const [badge, explanation] = verified ? explanations.verified
    : status !== 'verified' && Object.hasOwn(explanations, status) ? explanations[status]
      : ['Unverified', 'No completed verification is recorded. Treat this result as preliminary.']
  const links = [...new Set([
    ...(verified ? [sourceLink(job.source_urls.verified)] : []),
    sourceLink(job.source_urls.original), sourceLink(job.source_urls.description),
  ].filter((link): link is string => link !== null))]
  return <article className="job-card" aria-labelledby={`job-${rank}`}>
    <div className="job-heading">
      <span className="rank" aria-label={`Rank ${rank}`}>{String(rank).padStart(2, '0')}</span>
      <div className="job-identity"><p className="company">{job.company}</p><h3 id={`job-${rank}`}>{job.title}</h3>
        <p className="metadata">{job.location} <span aria-hidden="true">·</span> {job.employment_type || 'Type not specified'}</p></div>
      <span className={`badge ${verified ? 'verified' : 'preliminary'}`}>{badge}</span>
    </div>
    <div className="evidence-row">
      <div className="score preliminary-score"><span>Preliminary Match Score</span><strong>{job.preliminary_match_score ?? '—'}<small> / 100</small></strong></div>
      {verified && job.verified_match_score !== null
        ? <div className="score verified-score"><span>Verified Match Score</span><strong>{job.verified_match_score}<small> / 100</small></strong></div>
        : <div className="verification-note"><span className="eyebrow">Verification</span><p>No verified score available</p></div>}
      <div className="confidence"><span className="eyebrow">Confidence</span><p>{job.confidence || 'Not specified'}</p></div>
    </div>
    <p className="explanation">{demo && <strong>Simulated outcome. </strong>}{explanation}</p>
    <div className="skills-grid">
      <section><h4>Strengths</h4>{job.strengths.length ? <ul>{job.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul> : <p>None identified.</p>}</section>
      <section><h4>Missing skills</h4>{job.missing_skills.length ? <ul>{job.missing_skills.map((s, i) => <li key={i}>{s}</li>)}</ul> : <p>No missing skills identified; this is not a guarantee of fit.</p>}</section>
    </div>
    <footer className="job-footer"><p><span className="eyebrow">Recommendation</span>{recommendation}</p>
      <div className="source-links">{demo
        ? <span>Synthetic posting — no external source.</span>
        : links.length ? links.map((link, i) => <a key={link} href={link} target="_blank" rel="noopener noreferrer">{i === 0 ? 'View source' : 'Additional source'} <span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></a>) : <span>No source available</span>}</div>
    </footer>
  </article>
}
