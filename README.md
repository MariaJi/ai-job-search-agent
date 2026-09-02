# ai-job-search-agent
A LangGraph job-search and verification workflow with a FastAPI service. There
is no frontend or deployment configuration yet.

## Local API

Python 3.11+ is required. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Set `OPENAI_API_KEY`, `JOOBLE_API_KEY`, and `TAVILY_API_KEY` in your process
environment before starting a real search. Alternatively pass `--env-file .env`
to uvicorn to explicitly load your local ignored file. Never commit credentials
or resumes. Imports and health checks do not load `.env` or initialize providers.

`CORS_ORIGINS` is an optional comma-separated list of explicit origins, such as
`http://localhost:5173`. By default no cross-origin requests are allowed. Cookies/
credentialed CORS and wildcard origins are not enabled.

### Endpoints

- `GET /health` returns `{"status":"ok"}` without provider keys. It is a process
  health check, not a provider readiness check.
- `POST /api/v1/job-search` accepts multipart fields `resume` (DOCX) and
  `search_request` (1–2000 non-whitespace characters). Only these fields are
  supported. Use the DOCX MIME type or `application/octet-stream`.

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe -X POST http://127.0.0.1:8000/api/v1/job-search -F "search_request=Find remote Senior AI Engineer jobs from the last 7 days" -F "resume=@C:/path/to/your/resume.docx;type=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
```

The POST example makes live, potentially billable provider calls. Automated
tests do not. Interactive contract documentation is available at `/docs` and
the schema at `/openapi.json`.

**Do not publicly deploy the live endpoint without access and cost controls.**
CORS is not access control. The future public portfolio demo should use protected
live access or a safe sample/demo mode; neither is implemented yet. Responses
contain resume-derived personal information and should be treated as private.

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
multipart/request, 413 upload too large, 415 wrong file type, 422 invalid form or
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
