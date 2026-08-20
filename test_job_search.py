from dotenv import load_dotenv

load_dotenv()

from app.tools.job_search import search_jooble_jobs


result = search_jooble_jobs(
    keywords="Senior AI Engineer",
    location="Remote",
    results_per_page=3
)

print(result)