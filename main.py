
from dotenv import load_dotenv
import os
load_dotenv()

print("API key loaded:", bool(os.getenv("OPENAI_API_KEY")))
from app.graph import graph
print(graph.get_graph().draw_mermaid())


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
    "final_report": ""
}

result = graph.invoke(initial_state)
print("days_old:", result["days_old"])
print("jobs found:", len(result["jobs"]))

for analysis in result["analyses"]:
    print(analysis)
print("ranked jobs:", len(result["ranked_jobs"]))

print("selected jobs:", len(result["selected_jobs"]))

for job in result["selected_jobs"]:
    print(
        job["match_score"],
        "-",
        job["title"],
        "at",
        job["company"],
        "-",
        job["recommendation"]
    )

print("\nFINAL REPORT")
print(result["final_report"])