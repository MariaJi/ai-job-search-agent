from dotenv import load_dotenv

load_dotenv()

from app.tools.job_search import search_jooble_jobs

from app.tools.resume_reader import read_docx_resume

resume_text = read_docx_resume("data/resume.docx")

print(resume_text)

result = search_jooble_jobs(
    keywords="Senior AI Engineer",
    location="Remote",
    results_per_page=3
)

print(result)