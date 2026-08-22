from typing import TypedDict
from typing import TypedDict, Annotated
import operator
class Job(TypedDict):
    title: str
    company: str
    location: str
    description: str
    description_source: str
    description_complete: bool
    url: str
    updated_date: str

class JobSearchState(TypedDict):
    search_request: str
    role: str
    location: str
    employment_type: str
    days_old: int
    jobs: list[Job]
    current_job: Job | None
  
    analyses: Annotated[list[dict], operator.add]
    ranked_jobs: list[dict]
    selected_jobs: list[dict]
    final_report: str
    
    resume_text: str
    candidate_profile: dict
