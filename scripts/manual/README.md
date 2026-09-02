# Manual diagnostics

Run from the repository root with the project dependencies installed. Importing
these modules does nothing. Pytest excludes this directory; filenames do not
match pytest's test naming convention.

These commands are **manual and live** except for the local resume reader.
Jooble needs `JOOBLE_API_KEY`; source diagnostics and verification need
`TAVILY_API_KEY` and `OPENAI_API_KEY`. Provider credentials are read from the
environment (or local `.env` only after invocation), never embedded here.
Live commands can incur provider charges. They are not part of offline tests.

```powershell
python -m scripts.manual.jooble --keywords "Senior AI Engineer" --location Remote --limit 3
python -m scripts.manual.resume "PATH_TO_YOUR_RESUME.docx"
python -m scripts.manual.job_sources --title "Senior Software Engineer" --company "Example" --snippet "Known posting text"
python -m scripts.manual.job_sources --title "Senior Software Engineer" --company "Example" --snippet "Known posting text" --verify
```

Use `--source-url` with a company job-board root to inspect source-specific
search and exact-posting selection. Without it, the best ranked broad-search
source is extracted. Verification mode prints the complete verification result,
including status, description, provenance, and metadata.

Resume output is printed to your terminal only and is not sent to any provider.
Do not commit resumes, credentials, or diagnostic output containing private data.

Replaces the useful parts of the former `test_job_search.py`,
`test_resume_reader.py`, and `test_web_search.py`. The former
`test_verification.py` was a pure routing assertion, preserved in automated tests.
