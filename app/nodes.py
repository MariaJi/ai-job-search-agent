import os
from functools import lru_cache
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from app.tools.job_search import search_jooble_jobs
from app.state import JobSearchState, Job
from datetime import datetime, timedelta
from app.tools.web_search import (
    search_original_job,
    search_job_on_source,
    extract_job_description,
)
from difflib import SequenceMatcher
from langgraph.types import Send
import html
import re
from urllib.parse import urlparse
from app.constants import AnalysisType, VerificationStatus
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

class JobSourceMatch(BaseModel):
    is_same_job: bool
    confidence: str
    reason: str


class ExtractedJobValidation(BaseModel):
    is_same_job: bool
    confidence: str
    reason: str

class VerifiedJobMetadata(BaseModel):
    title: str
    company: str
    location: str
    employment_type: str | None = None

@lru_cache(maxsize=1)
def get_model():
    """Construct the provider only on first use, after configuration is loaded."""
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


@lru_cache(maxsize=None)
def get_structured_model(schema: type[BaseModel]):
    """Reuse each structured-output binding without changing provider defaults."""
    return get_model().with_structured_output(schema)

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

    criteria = get_structured_model(SearchCriteria).invoke(
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

    cutoff_date = datetime.now().astimezone() - timedelta(days=days_old)

    jobs = []

   
    for raw_job in raw_jobs:
        updated_text = raw_job.get("updated", "")

        if isinstance(updated_text, str) and updated_text:
            try:
                normalized_date = updated_text.replace("Z", "+00:00")
                updated_date = datetime.fromisoformat(normalized_date)

                if updated_date.tzinfo is None:
                    updated_date = updated_date.replace(
                        tzinfo=cutoff_date.tzinfo
                    )

                if updated_date < cutoff_date:
                    continue
            except (TypeError, ValueError):
                # Retain jobs with bad provider dates; preserve the raw value.
                pass

        job = {
            "title": raw_job.get("title", ""),
            "company": raw_job.get("company", ""),
            "location": raw_job.get("location", ""),
            "description": clean_html_text(raw_job.get("snippet", "")),
            "url": raw_job.get("link", ""),
            "source_url": raw_job.get("link", ""),
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

    profile = get_structured_model(CandidateProfile).invoke(
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

def evaluate_job_source_match(
    job: Job,
    search_result: dict
) -> JobSourceMatch:

    return get_structured_model(JobSourceMatch).invoke(
        f"""
        Determine whether this web search result is likely the same job
        as the original job posting.

        Original job:
        Title: {job["title"]}
        Company: {job["company"]}
        Location: {job["location"]}
        Description snippet: {job["description"]}

        Candidate web result:
        Title: {search_result["title"]}
        URL: {search_result["url"]}
        Content: {search_result["content"]}

        Rules:
        - Company names may vary slightly, such as "Tight" vs "Tight, Inc."
        - Job titles may vary in wording or punctuation.
        - Do not require exact title equality.
        - A clearly different company means this is not the same job.
        - Use title, company, location, and content together.
        - confidence must be one of: "High", "Medium", or "Low".
        """
    )

def normalize_company_name(name: str) -> str:
    name = name.lower()
    name = name.replace(",", "")
    name = name.replace(".", "")
    name = name.replace(" inc", "")
    name = name.replace(" llc", "")
    name = name.replace(" ltd", "")
    return name.strip()


def get_source_quality(url: str, company: str) -> int:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    normalized_company = normalize_company_name(company)

    trusted_ats = [
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "ashbyhq.com",
    ]

    secondary_sources = [
        "linkedin.com",
    ]

    aggregators = [
        "jooble.org",
        "jobleads.com",
        "grabjobs.co",
        "ziprecruiter.com",
        "indeed.com",
    ]

    # Likely company-owned domain
    company_token = normalized_company.replace(" ", "")

    if company_token and company_token in domain.replace("-", ""):
        return 4

    if any(source in domain for source in trusted_ats):
        return 3

    if any(source in domain for source in secondary_sources):
        return 2

    if any(source in domain for source in aggregators):
        return 1

    return 0

def get_title_match_score(
    original_title: str,
    candidate_title: str
) -> float:

    original = original_title.lower().strip()
    candidate = candidate_title.lower().strip()

    return SequenceMatcher(
        None,
        original,
        candidate
    ).ratio()


def rank_job_sources(
    job: Job,
    search_results: list[dict]
) -> list[dict]:

    matched_results = []

    confidence_rank = {
        "High": 3,
        "Medium": 2,
        "Low": 1,
    }

    for result in search_results:
        match = evaluate_job_source_match(
            job=job,
            search_result=result
        )

        if not match.is_same_job:
            continue

       

        confidence_score = confidence_rank.get(
            match.confidence,
            0
        ) 

        source_quality = get_source_quality(
            result["url"],
            job["company"]
        )

        title_match_score = get_title_match_score(
            job["title"],
            result["title"]
        )

        selection_score = (
            title_match_score * 0.6
            + (source_quality / 4) * 0.3
            + (confidence_score / 3) * 0.1
        )


        matched_results.append({
        "result": result,
        "confidence": match.confidence,
        "confidence_score": confidence_score,
        "title_match_score": title_match_score,
        "source_quality": source_quality,
        "selection_score": selection_score,
        "reason": match.reason,
        })

    if not matched_results:
         return []

    
   
    matched_results.sort(
        key=lambda item: item["selection_score"],
        reverse=True
    )
   
    return [
        {
            "title": item["result"]["title"],
            "url": item["result"]["url"],
            "content": item["result"]["content"],
            "match_confidence": item["confidence"],
            "source_quality": item["source_quality"],
            "selection_score": item["selection_score"],
            "match_reason": item["reason"],
        }
        for item in matched_results
    ]


def validate_extracted_job(
    job: Job,
    source: dict,
    extracted_description: str
) -> ExtractedJobValidation:

    validator = get_structured_model(
        ExtractedJobValidation
    )

    return validator.invoke(
        f"""
        Determine whether the extracted job description belongs to
        the SAME specific job as the original job candidate.

        ORIGINAL JOB

        Title:
        {job["title"]}

        Company:
        {job["company"]}

        Location:
        {job["location"]}

        Original description snippet:
        {job["description"]}


        CANDIDATE SOURCE

        Title:
        {source["title"]}

        URL:
        {source["url"]}


        EXTRACTED JOB DESCRIPTION

        {extracted_description}


        VALIDATION RULES

        - The company must match.
        - The role must represent the same specific position, not merely
          a similar job at the same company.
        - Compare the job title and seniority carefully.
        - Compare location or work arrangement when available.
        - Compare distinctive technologies, responsibilities, domain,
          team, and job-specific wording.
        - A slightly different title is acceptable when the responsibilities
          clearly identify the same position.
        - A similar role at the same company is NOT sufficient.
        - If important evidence conflicts, return is_same_job=False.
        - If there is not enough evidence to confidently establish that
          this is the same posting, return is_same_job=False.

        confidence must be one of:
        "High", "Medium", or "Low".
        """
    )

def select_exact_job_posting(
    job: Job,
    search_results: list[dict]
) -> dict | None:

    matched_results = []

    confidence_rank = {
        "High": 3,
        "Medium": 2,
        "Low": 1,
    }

    for result in search_results:
        match = evaluate_job_source_match(
            job=job,
            search_result=result,
        )

        if not match.is_same_job:
            continue

        matched_results.append({
            "result": result,
            "confidence": match.confidence,
            "confidence_score": confidence_rank.get(
                match.confidence,
                0
            ),
            "reason": match.reason,
        })

    if not matched_results:
        return None

    matched_results.sort(
        key=lambda item: item["confidence_score"],
        reverse=True,
    )

    best = matched_results[0]

    return {
        "title": best["result"]["title"],
        "url": best["result"]["url"],
        "content": best["result"]["content"],
        "match_confidence": best["confidence"],
        "match_reason": best["reason"],
    }



def get_verification_priority(
    job: Job,
    analysis: JobAnalysis,
    match_score: int
) -> str:

    if job["description_complete"]:
        return "Not Needed"

    if (
        match_score >= 85
        or (
            analysis.role_specific_score >= 15
            and analysis.technical_score >= 25
        )
    ):
        return "High"

    if (
        match_score >= 60
        or analysis.experience_score >= 20
        or analysis.confidence == "Low"
    ):
        return "Medium"

    return "Low"



def score_job(
    job: dict,
    candidate_profile: dict
) -> JobAnalysis:

        return get_structured_model(JobAnalysis).invoke(
        f"""
        Evaluate how well this candidate matches THIS specific job.

        Candidate profile:
        {candidate_profile}

        Job title:
        {job["title"]}

        Company:
        {job["company"]}

        Location:
        {job["location"]}

        Job description:
        {job["description"]}

        Description source:
        {job["description_source"]}

        Description complete:
        {job["description_complete"]}


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
            - be conservative about the assessment
            - confidence should normally be "Low" or "Medium"

        - If description_complete is True:
            - treat the description as the best available verified evidence
            - use explicit location and work-arrangement requirements
            - confidence may be "High" when the available evidence is clear

        - confidence must be one of:
            "High", "Medium", or "Low"

        - strengths must contain qualifications from the candidate profile
          that directly support this job.

        - missing_skills must contain important job requirements that are
          missing or not clearly demonstrated in the candidate profile.
        """
    )

 # analyze one current_job and return the result
def analyze_job(state: JobSearchState):

    current_job = state["current_job"]
    candidate_profile = state["candidate_profile"]

    if current_job is None:
        return {
            "analyses": []
        }

    analysis = score_job(
        current_job,
        candidate_profile
    )

    match_score = (
        analysis.technical_score
        + analysis.experience_score
        + analysis.role_specific_score
        + analysis.tools_platform_score
        + analysis.location_score
    )

    preliminary_match_score = match_score

    verification_status = (
        VerificationStatus.NOT_NEEDED
        if current_job["description_complete"]
        else VerificationStatus.PENDING
    )

    verification_priority = get_verification_priority(
        current_job,
        analysis,
        match_score
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
                "description": current_job["description"],
                "description_source": current_job["description_source"],
                "description_complete": current_job["description_complete"],
                "url": current_job["url"],
                "source_url": current_job["source_url"],
                "updated_date": current_job["updated_date"],

                "preliminary_match_score": preliminary_match_score,
                "match_score": match_score,

                "verification_status": verification_status,
                "verification_priority": verification_priority,
                "needs_verification": not current_job["description_complete"],

                "recommendation": recommendation,

                **analysis.model_dump()
            }
        ]
    }


def extract_verified_job_metadata(
    source: dict,
    extracted_description: str
) -> VerifiedJobMetadata:

    extractor = get_structured_model(
        VerifiedJobMetadata
    )

    return extractor.invoke(
        f"""
        Extract the job metadata from this verified job posting.

        SOURCE TITLE:
        {source["title"]}

        SOURCE URL:
        {source["url"]}

        FULL JOB DESCRIPTION:
        {extracted_description}

        Extract:
        - title
        - company
        - location
        - employment_type

        Rules:
        - Use only information supported by the job posting.
        - Do not guess missing information.
        - Preserve remote/hybrid information when stated.
        - employment_type should be values such as
          Full-time, Part-time, Contract, Temporary, or Internship.
        """
    )



def verify_job(state: JobSearchState):
    current_job = state["current_job"]

    if current_job is None:
        return {
            "verified_jobs": []
        }

    # Already complete — no verification needed.
    if current_job["description_complete"]:
        return {
            "verified_jobs": [
                {
                    **current_job,
                    "verification_status": VerificationStatus.NOT_NEEDED,
                }
            ]
        }

    try:
        # Step 1: broad web search
        search_results = search_original_job(
            title=current_job["title"],
            company=current_job["company"],
        )

        
        if not search_results:
            
            return {
                "verified_jobs": [
                    {
                        **current_job,
                        "verification_status": VerificationStatus.NOT_FOUND,
                    }
                ]
            }

        # Step 2: rank sources
        ranked_sources = rank_job_sources(
            job=current_job,
            search_results=search_results,
        )
        
        
        if not ranked_sources:
            return {
                "verified_jobs": [
                    {
                        **current_job,
                        "verification_status": VerificationStatus.NOT_FOUND,
                    }
                ]
            }

        successful_extraction = None
        description_source = None

        
        for source in ranked_sources:
            extraction = extract_job_description(
            source["url"]
            )

            if extraction["status"] != "success":
                continue

            validation = validate_extracted_job(
                job=current_job,
                source=source,
                extracted_description=extraction["content"],
            )

            if not validation.is_same_job:
                
                continue

          
            successful_extraction = extraction
            description_source = source
            break

        if successful_extraction is None:
            return {
                "verified_jobs": [
                    {
                        **current_job,
                        "verification_status": VerificationStatus.FAILED,
                    }
                ]
            }

        verified_metadata = extract_verified_job_metadata(
            source=description_source,
            extracted_description=successful_extraction["content"],
        )


        verified_job = {
            **current_job,

            "location": (
            verified_metadata.location
            or current_job["location"]
            ),

            "employment_type": (
            verified_metadata.employment_type
            or current_job.get("employment_type", "")
            ),

            "description": successful_extraction["content"],
            "description_source": successful_extraction["source"],
            "description_complete": True,

            "source_url": current_job.get(
                "source_url",
                current_job.get("url")
            ),
            "verified_url": description_source["url"],
            "description_url": description_source["url"],

            "verification_status": VerificationStatus.VERIFIED,
            "needs_verification": False,
        }
        return {
            "verified_jobs": [verified_job]
        }

    except Exception as exc:
        error_message = str(exc)

        # Provider exception text can contain request content or credentials.
        print("Verification unavailable; retaining preliminary results.")

        if (
            "usage limit" in error_message.lower()
            or "rate limit" in error_message.lower()
            or "quota" in error_message.lower()
        ):
            verification_status = VerificationStatus.SERVICE_ERROR
        else:
            verification_status = VerificationStatus.FAILED

        return {
            "verified_jobs": [
                {
                    **current_job,
                    "verification_status": verification_status,
                }
            ]
        }


def collect_verified_jobs(state: JobSearchState):
    return {}


def rank_jobs(state: JobSearchState):
    ranked = sorted(
        state["analyses"],
        key=lambda item: item["match_score"],
        reverse=True
    )

    return {
        "ranked_jobs": ranked
    }


def select_jobs_Old(state: JobSearchState):
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


def select_jobs(state: JobSearchState):
    selected = [
        job
        for job in state["final_ranked_jobs"]
        if (
            job["recommendation"] in ["Strong Apply", "Apply"]
            and job["match_score"] >= 75
        )
    ]

    selected = sorted(
        selected,
        key=lambda job: -job["match_score"]
    )

    return {
        "selected_jobs": selected
    }


def generate_report(state: JobSearchState):
    selected_jobs = state["selected_jobs"]
    verified_jobs = state["verified_jobs"]

    service_errors = [
        job
        for job in verified_jobs
        if job.get("verification_status") == VerificationStatus.SERVICE_ERROR
    ]
    service_warning = ""

    if service_errors:
        service_warning = (
            f"\n\nNote: {len(service_errors)} job(s) could not be verified "
            f"because the external verification service was unavailable "
            f"or reached its usage limit."
        )
   
    if (
        not selected_jobs
        and verified_jobs
        and len(service_errors) == len(verified_jobs)
    ):
        return {
            "final_report": (
                "Job verification could not be completed because "
                "the external verification service is unavailable "
                "or has reached its usage limit."
            )
        }
   
    if not state["jobs"]:
        return {
            "final_report": "No jobs were found for the requested criteria."
        }

    if not selected_jobs:
        return {
            "final_report": "No job matches met the application threshold."
        }

    lines = []

    for index, job in enumerate(selected_jobs, start=1):
        strengths = job.get("strengths", [])
        missing_skills = job.get("missing_skills", [])

        verification_status = VerificationStatus.normalize(
            job.get("verification_status")
        )
        analysis_type = job.get(
            "analysis_type",
            AnalysisType.VERIFIED
            if verification_status == VerificationStatus.VERIFIED
            else AnalysisType.PRELIMINARY,
        )
        if (
            analysis_type == AnalysisType.VERIFIED
            and verification_status == VerificationStatus.VERIFIED
        ):
            score_lines = (
                f"Verified Match Score: {job['match_score']}\n"
                f"Preliminary Match Score: "
                f"{job.get('preliminary_match_score', 'N/A')}\n"
            )
        else:
            score_lines = (
                f"Preliminary Match Score: {job['match_score']}\n"
                "Verified Match Score: Not available\n"
            )

        lines.append(
            f"{index}. {job['title']} at {job['company']}\n"
            f"{score_lines}"
            f"Recommendation: {job['recommendation']}\n"
            f"Confidence: {job['confidence']}\n"
            f"Location: {job['location']}\n"
            
            f"Employment Type: {job.get('employment_type') or 'N/A'}\n"
            f"Verification Status: {verification_status}\n"
            
            f"URL: {job.get('verified_url', job.get('url', 'N/A'))}\n"
            f"Strengths: {', '.join(strengths) if strengths else 'None listed'}\n"
            f"Missing Skills: {', '.join(missing_skills) if missing_skills else 'None identified'}\n"
        )

    return {
         "final_report": "\n".join(lines) + service_warning
    }


def select_verification_candidates(state: JobSearchState):
    max_verification_jobs = int(
        os.getenv("MAX_VERIFICATION_JOBS", "2")
    )

    candidates = [
        job
        for job in state["ranked_jobs"]
        if (
            job["needs_verification"]
            and job["verification_priority"] in ["High", "Medium"]
        )
    ]

    if max_verification_jobs <= 0:
        candidates = []
    else:
        candidates = candidates[:max_verification_jobs]

    return {
        "verification_candidates": candidates
    }

def send_verification_jobs(state: JobSearchState):
    if not state["verification_candidates"]:
        return "collect_verified_jobs"

    return [
        Send(
            "verify_job",
            {
                "current_job": job,
                "verified_jobs": [],
            }
        )
        for job in state["verification_candidates"]
    ]



def analyze_verified_job(state: JobSearchState):
    current_job = state["current_job"]
    candidate_profile = state["candidate_profile"]

    if current_job is None:
        return {
            "verified_analyses": []
        }

    if current_job.get("verification_status") != VerificationStatus.VERIFIED:
        return {
            "verified_analyses": []
        }

    analysis = score_job(
        current_job,
        candidate_profile
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
        "verified_analyses": [
            {
                **current_job,
                **analysis.model_dump(),

                "preliminary_match_score":
                    current_job["preliminary_match_score"],

                "match_score": match_score,

                "verification_status": VerificationStatus.VERIFIED,
                "needs_verification": False,
                "recommendation": recommendation,
            }
        ]
    }


def send_verified_jobs_for_analysis(state: JobSearchState):
    verified_jobs = [
        job
        for job in state["verified_jobs"]
        if job.get("verification_status") == VerificationStatus.VERIFIED
    ]

    if not verified_jobs:
        return "collect_verified_analyses"

    return [
        Send(
            "analyze_verified_job",
            {
                "current_job": job,
                "candidate_profile": state["candidate_profile"],
                "verified_analyses": [],
            }
        )
        for job in verified_jobs
    ]

def final_rank_jobs_Old(state: JobSearchState):
    verified_analyses = state["verified_analyses"]

    final_jobs = sorted(
        verified_analyses,
        key=lambda job: job["match_score"],
        reverse=True
    )

    return {
        "final_ranked_jobs": final_jobs
    }

def final_rank_jobs(state: JobSearchState):
    ranked_jobs = state["ranked_jobs"]
    verified_analyses = state["verified_analyses"]
    verified_jobs = state["verified_jobs"]

    def job_key(job: dict) -> str:
        return (
            job.get("source_url")
            or job.get("url")
            or f"{job.get('company', '')}:{job.get('title', '')}"
        )

    # Verified analysis wins when available.
    verified_by_key = {
        job_key(job): job
        for job in verified_analyses
    }

    # Preserve verification outcome even when verification did not succeed.
    verification_status_by_key = {
        job_key(job): job.get(
            "verification_status",
            VerificationStatus.FAILED
        )
        for job in verified_jobs
    }

    final_jobs = []

    for preliminary_job in ranked_jobs:
        key = job_key(preliminary_job)

        if key in verified_by_key:
            final_job = {
                **verified_by_key[key],
                "analysis_type": AnalysisType.VERIFIED,
            }

        else:
            final_job = {
                **preliminary_job,
                "verification_status":
                    verification_status_by_key.get(
                        key,
                        VerificationStatus.NOT_NEEDED
                        if preliminary_job.get("verification_status") == VerificationStatus.NOT_NEEDED
                        else VerificationStatus.NOT_ATTEMPTED
                    ),
                "analysis_type": AnalysisType.PRELIMINARY,
            }

        final_jobs.append(final_job)

    final_jobs = sorted(
        final_jobs,
        key=lambda job: job["match_score"],
        reverse=True
    )

    return {
        "final_ranked_jobs": final_jobs
    }


def collect_verified_analyses(state: JobSearchState):
    return {}
