from dotenv import load_dotenv

load_dotenv()

from app.tools.web_search import search_original_job
from app.nodes import evaluate_job_source_match

job = {
    "title": "AI-focused Senior Software Engineer",
    "company": "Tight",
    "location": "Remote",
    "description": (
        "AI-focused Senior Software Engineer. "
        "Tight Embedded Accounting. "
        "Engineering role focused on AI and software development."
    ),
    "description_source": "jooble_snippet",
    "description_complete": False,
    "source": "grabjobs.co",
    "url": "https://jooble.org/",
    "updated_date": "",
}



results = search_original_job(
    title=job["title"],
    company=job["company"],
)

for result in results:
    match = evaluate_job_source_match(
        job=job,
        search_result=result,
    )

    print("\nRESULT TITLE:", result["title"])
    print("URL:", result["url"])
    print("SAME JOB:", match.is_same_job)
    print("CONFIDENCE:", match.confidence)
    print("REASON:", match.reason)