
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
    "analysis_result": {}
}

result = graph.invoke(initial_state)
print("days_old:", result["days_old"])
print("jobs found:", len(result["jobs"]))
print(result)