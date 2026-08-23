from dotenv import load_dotenv

load_dotenv()
from urllib.parse import urlparse
from app.nodes import (
    evaluate_job_source_match,
    select_best_job_source,
   
)

from app.tools.web_search import (
    search_original_job,
    search_job_on_source,
)

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


best_source = select_best_job_source(
    job=job,
    search_results=results
)

print("\nBEST SOURCE:")
print(best_source)

if best_source:
    source_results = search_job_on_source(
        title=job["title"],
        company=job["company"],
        source_url=best_source["url"],
    )

    print("\nSOURCE-SPECIFIC RESULTS:")

    for result in source_results:
        print("\nTITLE:", result["title"])
        print("URL:", result["url"])
        print("CONTENT:", result["content"])

