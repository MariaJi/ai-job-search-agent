from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from app.tools.job_search import search_jooble_jobs
from app.state import JobSearchState
from datetime import datetime, timedelta

import html
import re

def clean_html_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


class SearchCriteria(BaseModel):
    role: str
    location: str
    employment_type: str
    days_old: int

class JobAnalysis(BaseModel):
    match_score: int
    strengths: list[str]
    missing_skills: list[str]
    recommendation: str


model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

structured_model = model.with_structured_output(SearchCriteria)
job_analysis_model = model.with_structured_output(JobAnalysis)

CANDIDATE_PROFILE = """
Senior Software Engineer with 10+ years of enterprise software development experience.

Core skills:
- C#, .NET, ASP.NET Core, Web API
- Python, FastAPI
- React, JavaScript
- SQL Server
- Azure
- Docker
- REST APIs
- LLM applications and RAG
- LangGraph and agentic AI

Additional strengths:
- Enterprise application development
- Full-stack development
- API integration
- Cloud-based application development
- AI application development
"""

def understand_search_request(state: JobSearchState):
    search_request = state["search_request"]

    criteria = structured_model.invoke(
    f"""
    Extract job search criteria from the user's request.

    User request:
    {search_request}

    Rules:
    - role:
        - Extract the requested job title or role.

    - location:
        - If the user says "remote", return "Remote".
        - If the user specifies a city, state, or country, return that location.
        - If no location preference is specified, return "Any".

    - employment_type:
        - Extract Full-time, Part-time, Contract, Internship, etc.
        - If not specified, return "Full-time".

    - days_old:
        - If the user says "today", return 1.
        - If the user says "last 3 days", return 3.
        - If the user says "last week", return 7.
        - If the user gives another number of days, return that number.
        - If no time range is specified, return 7.

    Do not treat "remote" as a missing location.
    """
    )
    
    return {
        "role": criteria.role,
        "location": criteria.location,
        "employment_type": criteria.employment_type,
        "days_old" : criteria.days_old
    }

def search_jobs(state: JobSearchState):
    role = state["role"]
    location = state["location"]
    days_old = state["days_old"]

    response = search_jooble_jobs(
        keywords=role,
        location=location,
        results_per_page=10
    )

    raw_jobs = response["jobs"]

    cutoff_date = datetime.now() - timedelta(days=days_old)

    jobs = []

    for raw_job in raw_jobs:
        updated_text = raw_job.get("updated", "")

        if updated_text:
            updated_date = datetime.fromisoformat(updated_text)

            if updated_date < cutoff_date:
                continue

        job = {
            "title": raw_job.get("title", ""),
            "company": raw_job.get("company", ""),
            "location": raw_job.get("location", ""),
            "description": clean_html_text(raw_job.get("snippet", "")),
            "url": raw_job.get("link", ""),
            "updated_date": updated_text
        }

        jobs.append(job)

    return {
        "jobs": jobs,
        "current_job": jobs[0] if jobs else None
    }

def analyze_job(state: JobSearchState):
    current_job = state["current_job"]

    if current_job is None:
        return {
            "analyses": []
        }

    analysis = job_analysis_model.invoke(
        f"""
        Evaluate how well this candidate matches the job.

        Candidate profile:
        {CANDIDATE_PROFILE}

        Job title:
        {current_job["title"]}

        Company:
        {current_job["company"]}

        Location:
        {current_job["location"]}

        Job description:
        {current_job["description"]}

        Rules:
        - match_score must be an integer from 0 to 100.
        - strengths should list the candidate qualifications that match the job.
        - missing_skills should list important job requirements that are missing or not clearly demonstrated in the candidate profile.
        - Do not assume the candidate has skills that are not stated in the candidate profile.
        - recommendation should be one of:
          "Strong Apply", "Apply", "Maybe", or "Skip".
        """
    )

    return {
    "analyses": [
        {
            "title": current_job["title"],
            "company": current_job["company"],
            "location": current_job["location"],
            "url": current_job["url"],
            **analysis.model_dump()
        }
    ]
}

def rank_jobs(state: JobSearchState):
    ranked = sorted(
        state["analyses"],
        key=lambda item: item["match_score"],
        reverse=True
    )

    return {
        "ranked_jobs": ranked
    }

def select_jobs(state: JobSearchState):
    selected = [
        job for job in state["ranked_jobs"]
        if job["recommendation"] in ["Strong Apply", "Apply"]
    ]

    return {
        "selected_jobs": selected
    }