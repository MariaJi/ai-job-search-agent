from dotenv import load_dotenv

load_dotenv()
from urllib.parse import urlparse

from app.nodes import (
    evaluate_job_source_match,
    select_best_job_source,
    select_exact_job_posting,
)
from app.tools.web_search import (
    search_original_job,
    search_job_on_source,
    extract_job_description,
    parse_job_description
)
from app.nodes import verify_job

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


exact_job = select_exact_job_posting(
    job=job,
    search_results=source_results,
)

if exact_job:
    extraction = extract_job_description(
        exact_job["url"]
    )

    print("\nEXTRACTION STATUS:")
    print(extraction["status"])
    print("SOURCE:", extraction["source"])

    if extraction["status"] == "success":
        print("\nFULL JOB DESCRIPTION:")
        print(extraction["content"])
    else:
        print("ERROR:", extraction.get("error"))



print("\n\n===== TEST VERIFY_JOB =====")

test_state = {
    "current_job": job,
}

verification_result = verify_job(test_state)

print("\nVERIFICATION RESULT:")

verified_job = verification_result["verified_jobs"][0]

print("Title:", verified_job["title"])
print("Company:", verified_job["company"])
print(
    "Verification status:",
    verified_job["verification_status"]
)
print(
    "Description complete:",
    verified_job["description_complete"]
)
print(
    "Description source:",
    verified_job["description_source"]
)
print("URL:", verified_job["url"])

print("\nDESCRIPTION:")
print(verified_job["description"])