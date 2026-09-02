from typing import TypedDict, Annotated
import operator

class Job(TypedDict):
    title: str
    company: str
    location: str
    description: str
    description_source: str
    description_complete: bool
    source: str
    url: str
    source_url: str
    updated_date: str

class JobSearchState(TypedDict):
    search_request: str
    role: str
    location: str
    employment_type: str
    days_old: int

    jobs: list[Job]
    current_job: Job | None

    resume_text: str
    candidate_profile: dict

    analyses: Annotated[list[dict], operator.add]
    ranked_jobs: list[dict]

    verification_candidates: list[dict]
    verified_jobs: Annotated[list[dict], operator.add]
    verified_analyses: Annotated[list[dict], operator.add]

    final_ranked_jobs: list[dict]
    selected_jobs: list[dict]

    final_report: str
