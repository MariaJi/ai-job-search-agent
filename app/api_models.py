"""Public API contract: never serialize the internal graph state directly."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    search_request: str = Field(min_length=1, max_length=2000)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SearchCriteriaResponse(BaseModel):
    role: str
    location: str
    employment_type: str
    days_old: int


class CandidateSummary(BaseModel):
    summary: str
    years_experience: int | None = None


class SourceURLs(BaseModel):
    original: str | None = None
    verified: str | None = None
    description: str | None = None


class RankedJobResponse(BaseModel):
    title: str
    company: str
    location: str
    employment_type: str | None = None
    verification_status: str
    analysis_type: Literal["preliminary", "verified"]
    preliminary_match_score: int | None = Field(default=None, ge=0, le=100)
    verified_match_score: int | None = Field(default=None, ge=0, le=100)
    confidence: str
    strengths: list[str]
    missing_skills: list[str]
    recommendation: str
    source_urls: SourceURLs


class RunSummary(BaseModel):
    status: Literal["completed", "partial"]
    jobs_found: int
    jobs_analyzed: int
    verification_attempted: int
    verified_jobs: int
    preliminary_jobs: int
    selected_jobs: int
    returned_jobs: int
    warnings: list[str]


class JobSearchResponse(BaseModel):
    criteria: SearchCriteriaResponse
    candidate_profile: CandidateSummary
    ranked_jobs: list[RankedJobResponse]
    run_summary: RunSummary
