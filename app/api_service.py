"""Workflow boundary and explicit projection from internal state to API models."""

import os
from urllib.parse import parse_qsl, urlsplit

from app.api_models import (
    CandidateSummary, JobSearchResponse, RankedJobResponse,
    RunSummary, SearchCriteriaResponse, SourceURLs,
)
from app.constants import AnalysisType, VerificationStatus
from app.state import build_initial_state
from app.live_config import max_search_jobs, openai_max_retries, tavily_max_results


class ProviderConfigurationError(Exception):
    pass


class ProviderServiceError(Exception):
    pass


def run_workflow(search_request: str, resume_text: str) -> dict:
    """Keep configuration checks and provider imports off the health path."""
    try:
        max_search_jobs()
        openai_max_retries()
        verification_limit = int(os.getenv("MAX_VERIFICATION_JOBS", "2"))
        tavily_max_results()
    except ValueError:
        raise ProviderConfigurationError from None
    if verification_limit < 0:
        raise ProviderConfigurationError
    required = ["OPENAI_API_KEY", "JOOBLE_API_KEY"]
    if verification_limit > 0:
        required.append("TAVILY_API_KEY")
    if any(not os.getenv(name, "").strip() for name in required):
        raise ProviderConfigurationError

    import httpx
    import requests
    from openai import OpenAIError
    from langchain_core.exceptions import OutputParserException
    from pydantic import ValidationError
    from app.graph import graph

    try:
        return graph.invoke(build_initial_state(search_request, resume_text))
    except (OpenAIError, requests.RequestException, httpx.HTTPError,
            OutputParserException, ValidationError):
        raise ProviderServiceError from None


def public_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        parsed.port  # Reject malformed/out-of-range ports instead of returning broken links.
        sensitive_parameters = {
            "apikey", "key", "token", "accesstoken", "secret", "authorization",
            "auth", "password", "signature", "sig", "credential",
            "xamzsignature", "xamzcredential", "xgoogsignature", "xgoogcredential",
        }
        parameters = parse_qsl(parsed.query) + parse_qsl(parsed.fragment)
        if any(name.lower().replace("_", "").replace("-", "") in sensitive_parameters
               for name, _ in parameters):
            return None
    except ValueError:
        return None
    return value


def public_recommendation(value: object, *, verified: bool) -> str:
    """Public action wording is evidence-gated, not arbitrary model output."""
    if verified:
        if value in ("Apply", "Strong Apply"):
            return "Apply"
        if value in ("Maybe", "Skip"):
            return value
    return "Review original posting"


def build_response(state: dict) -> JobSearchResponse:
    jobs = []
    for job in state["final_ranked_jobs"]:
        status = VerificationStatus.normalize(job.get("verification_status"))
        is_verified = (
            status == VerificationStatus.VERIFIED
            and job.get("analysis_type", AnalysisType.VERIFIED) == AnalysisType.VERIFIED
        )
        jobs.append(RankedJobResponse(
            title=job["title"], company=job["company"], location=job["location"],
            employment_type=job.get("employment_type"),
            verification_status=status,
            analysis_type=AnalysisType.VERIFIED if is_verified else AnalysisType.PRELIMINARY,
            preliminary_match_score=(job.get("preliminary_match_score") if is_verified
                                     else job["match_score"]),
            verified_match_score=job["match_score"] if is_verified else None,
            confidence=job["confidence"], strengths=job.get("strengths", []),
            missing_skills=job.get("missing_skills", []),
            recommendation=public_recommendation(job.get("recommendation"), verified=is_verified),
            source_urls=SourceURLs(
                original=public_url(job.get("source_url") or job.get("url")),
                verified=public_url(job.get("verified_url")) if is_verified else None,
                description=public_url(job.get("description_url")),
            ),
        ))
    incomplete = any(
        job.get("verification_status") not in (
            VerificationStatus.VERIFIED, VerificationStatus.NOT_NEEDED,
        ) for job in state["verified_jobs"]
    )
    verified_count = sum(job.verified_match_score is not None for job in jobs)
    profile = state["candidate_profile"]
    return JobSearchResponse(
        criteria=SearchCriteriaResponse(
            role=state["role"], location=state["location"],
            employment_type=state["employment_type"], days_old=state["days_old"],
        ),
        candidate_profile=CandidateSummary(
            summary=profile["summary"], years_experience=profile.get("years_experience"),
        ),
        ranked_jobs=jobs,
        run_summary=RunSummary(
            status="partial" if incomplete else "completed",
            jobs_found=len(state["jobs"]), jobs_analyzed=len(state["analyses"]),
            verification_attempted=len(state["verification_candidates"]),
            verified_jobs=verified_count, preliminary_jobs=len(jobs) - verified_count,
            selected_jobs=len(state["selected_jobs"]), returned_jobs=len(jobs),
            warnings=["Some jobs could not be verified; preliminary scores were retained."]
            if incomplete else [],
        ),
    )
