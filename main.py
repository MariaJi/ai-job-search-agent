
from dotenv import load_dotenv
import os
load_dotenv()

print("API key loaded:", bool(os.getenv("OPENAI_API_KEY")))
from app.graph import graph
print(graph.get_graph().draw_mermaid())

from app.tools.resume_reader import read_docx_resume

resume_text = read_docx_resume("data/resume.docx")

initial_state = {
   "search_request": "Find remote Senior AI Engineer jobs from the last 1 day",
    "role": "",
    "location": "",
    "employment_type": "",
    "days_old": 7,
    "jobs": [],
    "current_job": None,
    
    "analyses": [],
    "ranked_jobs": [],
    "selected_jobs": [],
    "final_report": "",
    "resume_text": resume_text,
    "candidate_profile": {},
}

result = graph.invoke(initial_state)
print("days_old:", result["days_old"])
print("jobs found:", len(result["jobs"]))



for job in result["analyses"]:
    print(
        job["title"],
        "- preliminary:", job["preliminary_match_score"],
        "- current:", job["match_score"],
        "- priority:", job["verification_priority"],
        "- status:", job["verification_status"],
        "- needs verification:", job["needs_verification"],
    )   

print("ranked jobs:", len(result["ranked_jobs"]))

print("selected jobs:", len(result["selected_jobs"]))


for job in result["selected_jobs"]:
    print(
        job["match_score"],
        "-",
        job["title"],
        "- Technical:", job["technical_score"],
        "- Experience:", job["experience_score"],
        "- Role-specific:", job["role_specific_score"],
        "- Tools/Platform:", job["tools_platform_score"],
        "- Location:", job["location_score"],
        "- Confidence:", job["confidence"],
    )

print("\nFINAL REPORT")
print(result["final_report"])

