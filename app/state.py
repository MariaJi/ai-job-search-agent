from typing import TypedDict, Annotated
import operator

class Job(TypedDict):
    job_id: str
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


def build_initial_state(search_request: str, resume_text: str) -> JobSearchState:
    return {
        "search_request": search_request,
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
