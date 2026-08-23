from pydantic import BaseModel, Field
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
    technical_score: int = Field(ge=0, le=40)
    experience_score: int = Field(ge=0, le=25)
    role_specific_score: int = Field(ge=0, le=20)
    tools_platform_score: int = Field(ge=0, le=10)
    location_score: int = Field(ge=0, le=5)

    confidence: str
    strengths: list[str]
    missing_skills: list[str]


class CandidateProfile(BaseModel):
    summary: str
    years_experience: int
    technical_skills: list[str]
    ai_skills: list[str]
    cloud_skills: list[str]
    domain_experience: list[str]
    education: list[str]

model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

structured_model = model.with_structured_output(SearchCriteria)
job_analysis_model = model.with_structured_output(JobAnalysis)
candidate_profile_model = model.with_structured_output(CandidateProfile)

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
            "updated_date": updated_text,
            "source": raw_job.get("source", ""),
            "description_source": "jooble_snippet",
            "description_complete": False,
        }

        jobs.append(job)

    return {
        "jobs": jobs,
        "current_job": jobs[0] if jobs else None
    }

def extract_candidate_profile(state: JobSearchState):
    resume_text = state["resume_text"]

    profile = candidate_profile_model.invoke(
        f"""
        Extract a structured candidate profile from this resume.

        Resume:
        {resume_text}

        Rules:
        - Summarize the candidate's professional background.
        - Estimate years_experience from the resume.
        - Extract technical skills.
        - Extract AI/ML/LLM-related skills separately.
        - Extract cloud skills separately.
        - Extract major domain/industry experience.
        - Extract education.
        - Do not invent skills or experience that are not supported by the resume.
        """
    )

    return {
        "candidate_profile": profile.model_dump()
    }

def analyze_job(state: JobSearchState):

    current_job = state["current_job"]
    candidate_profile = state["candidate_profile"]

    if current_job is None:
        return {
            "analyses": []
        }


    analysis = job_analysis_model.invoke(
    f"""
    Evaluate how well this candidate matches THIS specific job.

    Candidate profile:
    {candidate_profile}

    Job title:
    {current_job["title"]}

    Company:
    {current_job["company"]}

    Location:
    {current_job["location"]}

    Job description:
    {current_job["description"]}

    Description source:
    {current_job["description_source"]}

    Description complete:
    {current_job["description_complete"]}


    SCORING GUIDANCE

    technical_score (0-40):
    - Evaluate the candidate's broader technical capability against the
      core technical responsibilities of this job.
    - Consider software engineering depth, architecture, development,
      integration, problem solving, and other core technical capabilities
      relevant to this job.
    - Do not give points simply because the candidate has strong technical
      skills that this job does not require.
    - Do not double-count specific named tools, frameworks, or platforms
      that belong in tools_platform_score.
    - 35-40: excellent match
    - 25-34: strong match with some gaps
    - 15-24: partial match
    - 0-14: weak match


    experience_score (0-25):
    - Evaluate years of experience, seniority, responsibilities, and
      relevant professional background.
    - Consider whether the candidate's experience level matches what
      THIS job requires.
    - 22-25: very strong experience match
    - 15-21: generally relevant experience
    - 8-14: partially relevant experience
    - 0-7: weak experience match


    role_specific_score (0-20):
    - Identify the specialized capabilities that are particularly important
      to THIS specific role from the job description.
    - Score how well the candidate demonstrates those capabilities.
    - The specialty depends on the job.
    - For example, an AI role may emphasize LLM/RAG/ML capabilities,
      while a backend role may emphasize API architecture, distributed
      systems, or enterprise integration.
    - Do not assume AI, cloud, or any other specialty is required unless
      the job description indicates it.
    - Do not double-count general technical skills already evaluated in
      technical_score.
    - 17-20: very strong match
    - 10-16: moderate match
    - 1-9: limited match
    - 0: no demonstrated match


    tools_platform_score (0-10):
    - Evaluate explicitly requested tools, frameworks, platforms,
      databases, cloud services, libraries, and development technologies.
    - Only evaluate technologies relevant to THIS job.
    - Compare those technologies against technologies explicitly
      demonstrated in the candidate profile.
    - Do not double-count broader technical capability already evaluated
      in technical_score or role_specific_score.
    - 8-10: strong match
    - 4-7: partial match
    - 1-3: weak match
    - 0: no demonstrated match


    location_score (0-5):
    - Evaluate whether the job's location and work arrangement fit
      the candidate.
    - 5: clearly compatible
    - 3: unclear or potentially compatible
    - 0: clearly incompatible


    IMPORTANT SCORING RULES

    - Score against THIS job's requirements, not against a generic ideal
      candidate.
    - Do not reward a candidate skill unless it is relevant to this job.
    - Do not invent candidate skills or experience.
    - Do not assume missing job requirements.
    - Avoid double-counting the same qualification across categories.
    - Missing information is not evidence of a match.

    - If description_complete is False:
        - treat the analysis as preliminary
        - score only against requirements actually visible
        - do not assume the snippet contains all requirements
        - be conservative about the recommendation
        - confidence should normally be "Low" or "Medium"

    - confidence must be one of:
        "High", "Medium", or "Low"

    - strengths must contain qualifications from the candidate profile
      that directly support this job.

    - missing_skills must contain important job requirements that are
      missing or not clearly demonstrated in the candidate profile.

    """
    )   

    
    match_score = (
        analysis.technical_score
        + analysis.experience_score
        + analysis.role_specific_score
        + analysis.tools_platform_score
        + analysis.location_score
    )

    if match_score >= 90 and analysis.confidence == "High":
        recommendation = "Strong Apply"
    elif match_score >= 75:
        recommendation = "Apply"
    elif match_score >= 60:
        recommendation = "Maybe"
    else:
        recommendation = "Skip"

    return {
    "analyses": [
        {
            "title": current_job["title"],
            "company": current_job["company"],
            "location": current_job["location"],
            "url": current_job["url"],
            "match_score": match_score,
            "recommendation": recommendation,
            "needs_verification": not current_job["description_complete"],
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
        job
        for job in state["ranked_jobs"]
        if (
            job["recommendation"] in ["Strong Apply", "Apply"]
            and job["match_score"] >= 75
        )
    ]

    def job_sort_key(job):
        return (
            job["needs_verification"],
            -job["match_score"]
        )

    selected = sorted(
        selected,
        key=job_sort_key
    )

    return {
        "selected_jobs": selected
    }


def generate_report(state: JobSearchState):
    selected_jobs = state["selected_jobs"]

    if not selected_jobs:
        return {
            "final_report": "No strong job matches were found."
        }

    lines = []

    for job in selected_jobs:
        lines.append(
            f"{job['match_score']} - "
            f"{job['title']} at {job['company']} - "
            f"{job['recommendation']}\n"
            f"Confidence: {job['confidence']}\n"
            f"Needs verification: "
            f"{'Yes' if job['needs_verification'] else 'No'}\n"
            f"Location: {job['location']}\n"
            f"URL: {job['url']}\n\n"
        )

    return {
        "final_report": "\n".join(lines)
    }