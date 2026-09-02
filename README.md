# ai-job-search-agent
A LangGraph job-search and verification workflow with a FastAPI service and a
React + TypeScript workspace. Includes a synthetic, key-free sample mode. No
deployment configuration or automatic application submission is included.

## Local API

Python 3.11+ is required. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:CORS_ORIGINS="http://localhost:5173"
$env:ENABLE_LIVE_SEARCH="false"
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

For private local live use, set `ENABLE_LIVE_SEARCH=true` plus `OPENAI_API_KEY`,
`JOOBLE_API_KEY`, and `TAVILY_API_KEY` in your process environment and restart
the API. Alternatively pass `--env-file .env`
to uvicorn to explicitly load your local ignored file. Never commit credentials
or resumes. Imports and health checks do not load `.env` or initialize providers.

`CORS_ORIGINS` is an optional comma-separated list of explicit origins, such as
`http://localhost:5173`. By default no cross-origin requests are allowed. Cookies/
credentialed CORS and wildcard origins are not enabled.

### Endpoints

- `GET /health` returns `{"status":"ok"}` without provider keys. It is a process
  health check, not a provider readiness check.
- `GET /api/v1/demo` returns the same public response schema as live search,
  using `app/fixtures/demo.json`. All profiles, companies, jobs, scores, and
  verification outcomes are invented; source links use reserved `example.com`.
  It requires no keys, receives no resume, and makes no external calls.
- `POST /api/v1/job-search` accepts multipart fields `resume` (DOCX) and
  `search_request` (1–2000 non-whitespace characters). Only these fields are
  supported. Use the DOCX MIME type or `application/octet-stream`.

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/v1/demo
# Live must be explicitly enabled on the API before this command can run:
curl.exe -X POST http://127.0.0.1:8000/api/v1/job-search -F "search_request=Find remote Senior AI Engineer jobs from the last 7 days" -F "resume=@C:/path/to/your/resume.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

The POST example makes live, potentially billable provider calls. Automated
tests do not. Interactive contract documentation is available at `/docs` and
the schema at `/openapi.json`.

**Do not publicly deploy the live endpoint without access and cost controls.**
CORS and frontend flags are not access control. The API now defaults to
`ENABLE_LIVE_SEARCH=false`: POST requests are rejected with HTTP 403 before
reading the upload or invoking providers, even when keys are configured. Keep
this off for a public sample demo. A future public live demo still needs protected
access and cost controls, which are not implemented. Live responses contain
resume-derived personal information and should be treated as private.

Uploads are limited to 5 MiB, the entire multipart body to 5 MiB + 64 KiB, and
expanded DOCX archives to 20 MiB/1000 entries. No permanent file is saved;
multipart temporary uploads are closed on success and failure, and DOCX parsing
uses bounded member reads and an in-memory ZIP before DOCX parsing. Duplicate ZIP
members and oversized expanded archives are rejected. The reader extracts body
paragraphs and tables in document order (row-major within tables), including
nested tables without repeating merged cells. Headers/footers and scanned images
are excluded; empty/unreadable documents are rejected.

The response has four top-level fields:

| Field | Contents |
| --- | --- |
| `criteria` | Parsed role, location, employment type, days old |
| `candidate_profile` | Summary and years of experience; no raw resume |
| `ranked_jobs` | Final graph ordering, status, analysis type, separate preliminary/verified scores, confidence, strengths, missing skills, recommendation, source URLs |
| `run_summary` | Counts, `completed`/`partial` status, and safe verification warnings |

A numeric `verified_match_score` requires explicit `verification_status=verified`
and a verified analysis. Otherwise it is `null` and the score is preliminary.
Missing/unknown statuses normalize to `unverified`. `not_needed` means a complete
description skipped verification; it does not certify a verified score. Empty
results return HTTP 200 with empty arrays. Failed per-job verifications retain
preliminary results and return HTTP 200 with a `partial` run summary.

Errors use `{"error":{"code":"...","message":"..."}}`, with no provider
exception text, resume contents, or stack traces. Status codes: 400 malformed
multipart/request, 403 live search disabled, 413 upload too large, 415 wrong file type, 422 invalid form or
unreadable DOCX, 503 missing/invalid provider configuration, 502 provider failure,
and 500 unexpected internal failure.

Each request runs the existing graph in a worker thread and waits for completion;
there is no background queue, streaming, persistence, or authentication. Bind to
localhost for development. Slow providers can make requests take a long time.
Per-request result/verification limits are intentionally not exposed: the graph
fetches up to 10 jobs and uses server-level `MAX_VERIFICATION_JOBS` (default 2,
non-negative) and `TAVILY_MAX_RESULTS` (default 5, 1–20). Tavily configuration is
optional when `MAX_VERIFICATION_JOBS=0`. Do not change global configuration
between concurrent requests.

### Offline tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests mock workflow/provider boundaries, block network connections, and generate
synthetic DOCX data in memory. They never read a private resume. Optional live
diagnostics are documented separately in `scripts/manual/README.md`.

## Frontend and local full-stack startup

Use Node.js 22.12+ (tested with 22.17.1) and npm. Start the API above in one
terminal, then use a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. The Vite port is fixed so it matches the explicit
CORS origin; stop a conflicting server instead of silently changing ports.
The API defaults to `http://127.0.0.1:8000`. No provider keys are needed for
**Try Sample Demo**. Initial page load makes no search requests.

Optional settings are documented in `frontend/.env.example`. Put overrides in
ignored `frontend/.env.local` or the terminal environment, then restart Vite:

| Setting | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | API origin, without a trailing slash |
| `VITE_ENABLE_LIVE_SEARCH` | `false` | Only the exact value `true` enables live upload/submission controls |
| `ENABLE_LIVE_SEARCH` (backend) | `false` | Enables the paid POST endpoint only when set to `true`; read at app creation |
| `CORS_ORIGINS` (backend) | empty | Set `http://localhost:5173` for local Vite; never use a wildcard |

`VITE_*` values are public build-time configuration. Never put provider keys or
other secrets in them. The frontend flag is a UX safeguard, not a security
boundary: the backend flag must also stay off for sample-only access. To enable
local live use, set both live flags to `true`, configure provider keys only on the
backend, and restart both processes. Production builds capture the Vite flags
when `npm run build` runs; changing server environment later does not alter them.

The UI validates DOCX extension, MIME type, empty files, and the 5 MiB limit;
the backend also validates document contents and expanded ZIP size. File selection
is in memory only and is cleared after a live request completes or fails. No
resume text is displayed, and no upload or result is written to browser storage,
logs, or analytics. Candidate summaries are visible only in the returned results.
Live requests may take several minutes. There are no fake progress percentages
or automatic retries. Leaving the page aborts the browser request but **does not
guarantee cancellation of already-running provider work or charges**.

Cards separate preliminary and verified scores. Missing/unknown statuses never
display a verified score. The `not_needed` badge means a complete job description
was available, so verification was skipped; it remains preliminary. Confidence
and recommendations are workflow judgments, not calibrated hiring probabilities.
Demo verification and confidence are explicitly simulated.

### Frontend validation

```powershell
cd frontend
npm test
npm run lint
npm run build
npm ls --all
npm audit
```

Tests mock fetch and use synthetic fixtures only. `npm audit` contacts the npm
advisory service, not job-search providers. From the repository root, also run
`.venv\Scripts\python.exe -m pip check` and `git diff --check`. Build output and
dependencies are ignored; `package-lock.json` is tracked for reproducible installs.
