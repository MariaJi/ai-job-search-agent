from typing import TypedDict
class Job(TypedDict):
    title: str
    company: str
    location: str
    description: str
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
    analysis_result: str