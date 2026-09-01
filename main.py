
from dotenv import load_dotenv
import os
load_dotenv()

print("API key loaded:", bool(os.getenv("OPENAI_API_KEY")))
from app.graph import graph
print(graph.get_graph().draw_mermaid())

from app.tools.resume_reader import read_docx_resume

resume_text = read_docx_resume("data/resume.docx")



initial_state = {
    "search_request": "Find remote Senior AI Engineer jobs from the last 7 days",
    "role": "",
    "location": "",
    "employment_type": "",
    "days_old": 7,

    "jobs": [],
    "current_job": None,

    "resume_text": resume_text,
    "candidate_profile": {},

    "analyses": [],
    "ranked_jobs": [],

    "verification_candidates": [],
    "verified_jobs": [],
    "verified_analyses": [],

    "final_ranked_jobs": [],
    "selected_jobs": [],

    "final_report": "",
}

result = graph.invoke(initial_state)
print("\nFINAL REPORT\n")
print(result["final_report"])
print(
    "verification_candidates:",
    len(result["verification_candidates"])
)
print("days_old:", result["days_old"])
print("jobs found:", len(result["jobs"]))

print("\nPIPELINE COUNTS")
print("jobs:", len(result.get("jobs", [])))
print("analyses:", len(result.get("analyses", [])))
print("ranked_jobs:", len(result.get("ranked_jobs", [])))
print(
    "verification_candidates:",
    len(result.get("verification_candidates", []))
)
print(
    "verified_jobs:",
    len(result.get("verified_jobs", []))
)
print(
    "verified_analyses:",
    len(result.get("verified_analyses", []))
)
print(
    "final_ranked_jobs:",
    len(result.get("final_ranked_jobs", []))
)
print(
    "selected_jobs:",
    len(result.get("selected_jobs", []))
)


print("\nVERIFIED JOBS")

for job in result.get("verified_jobs", []):
    print(
        job["title"],
        "- status:",
        job.get("verification_status"),
        "- complete:",
        job.get("description_complete"),
    )

print("\nFINAL VERIFIED JOBS")

for job in result.get("final_ranked_jobs", []):
    print(
        job["title"],
        "- preliminary:",
        job.get("preliminary_match_score"),
        "- verified:",
        job.get("match_score"),
        "- status:",
        job.get("verification_status"),
    )   

