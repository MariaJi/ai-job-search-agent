from datetime import datetime, timedelta, timezone
import importlib

import pytest

from app.constants import AnalysisType, VerificationStatus
from app import nodes
from app.tools import web_search


def make_state(**overrides):
    state = {
        "search_request": "Find remote AI jobs",
        "role": "AI Engineer",
        "location": "Remote",
        "employment_type": "Full-time",
        "days_old": 7,
        "jobs": [],
        "current_job": None,
        "resume_text": "Python engineer",
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
    state.update(overrides)
    return state


def raw_job(updated):
    return {
        "title": "AI Engineer",
        "company": "Example",
        "location": "Remote",
        "snippet": "Build AI systems",
        "link": "https://example.com/jobs/1",
        "source": "example",
        "updated": updated,
    }


@pytest.mark.parametrize(
    "updated",
    [
        None,
        "",
        42,
        {"unexpected": "date object"},
        "not-a-date",
        datetime.now(timezone.utc).isoformat(),
        datetime.now().isoformat(),
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    ],
)
def test_search_jobs_tolerates_missing_malformed_and_mixed_dates(
    monkeypatch, updated
):
    monkeypatch.setattr(
        nodes,
        "search_jooble_jobs",
        lambda **kwargs: {"jobs": [raw_job(updated)]},
    )

    result = nodes.search_jobs(make_state())

    assert len(result["jobs"]) == 1


def test_search_jobs_filters_an_old_timezone_aware_job(monkeypatch):
    old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    monkeypatch.setattr(
        nodes,
        "search_jooble_jobs",
        lambda **kwargs: {"jobs": [raw_job(old_date)]},
    )

    assert nodes.search_jobs(make_state())["jobs"] == []


@pytest.mark.parametrize("failure_at", ["construction", "extraction"])
def test_tavily_exception_falls_back_to_direct_http(monkeypatch, failure_at):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    class FailingClient:
        def __init__(self, api_key):
            if failure_at == "construction":
                raise RuntimeError("Tavily unavailable")

        def extract(self, urls):
            raise RuntimeError("Tavily unavailable")

    class Response:
        text = (
            '<script type="application/ld+json">'
            '{"@type":"JobPosting","description":"<p>Build AI systems</p>"}'
            "</script>"
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(web_search, "TavilyClient", FailingClient)
    monkeypatch.setattr(
        web_search.requests, "get", lambda *args, **kwargs: Response()
    )

    result = web_search.extract_job_description("https://example.com/job")

    assert result == {
        "status": "success",
        "content": "Build AI systems",
        "source": "direct_http",
    }


def test_report_labels_preliminary_and_verified_scores():
    preliminary = {
        "title": "Job A",
        "company": "Example",
        "match_score": 80,
        "recommendation": "Apply",
        "confidence": "Medium",
        "location": "Remote",
        "url": "https://example.com/a",
        "analysis_type": AnalysisType.PRELIMINARY,
        "verification_status": VerificationStatus.NOT_ATTEMPTED,
    }
    verified = {
        **preliminary,
        "title": "Job B",
        "match_score": 90,
        "preliminary_match_score": 82,
        "analysis_type": AnalysisType.VERIFIED,
        "verification_status": VerificationStatus.VERIFIED,
    }

    report = nodes.generate_report(
        make_state(
            jobs=[preliminary, verified],
            selected_jobs=[preliminary, verified],
        )
    )["final_report"]

    assert (
        "Preliminary Match Score: 80\nVerified Match Score: Not available"
        in report
    )
    assert "Verified Match Score: 90\nPreliminary Match Score: 82" in report


def test_main_import_has_no_side_effects(capsys):
    module = importlib.import_module("main")
    importlib.reload(module)

    assert callable(module.main)
    assert capsys.readouterr() == ("", "")


def test_model_factories_are_lazy_cached_and_preserve_configuration(monkeypatch):
    from unittest.mock import Mock

    provider = Mock()
    constructor = Mock(return_value=provider)
    monkeypatch.setattr(nodes, "ChatOpenAI", constructor)
    nodes.get_structured_model.cache_clear()
    nodes.get_model.cache_clear()
    try:
        constructor.assert_not_called()
        schemas = (
            nodes.SearchCriteria, nodes.CandidateProfile, nodes.JobAnalysis,
            nodes.JobSourceMatch, nodes.ExtractedJobValidation,
            nodes.VerifiedJobMetadata,
        )
        for schema in schemas:
            first = nodes.get_structured_model(schema)
            assert nodes.get_structured_model(schema) is first
        constructor.assert_called_once_with(model="gpt-4o-mini", temperature=0, max_retries=2)
        assert provider.with_structured_output.call_count == len(schemas)
        assert [call.args[0] for call in provider.with_structured_output.call_args_list] == list(schemas)
    finally:
        nodes.get_structured_model.cache_clear()
        nodes.get_model.cache_clear()


def test_send_verified_jobs_filters_failures():
    verified = {"title": "A", "verification_status": VerificationStatus.VERIFIED}
    sends = nodes.send_verified_jobs_for_analysis(make_state(verified_jobs=[
        verified,
        {"title": "B", "verification_status": VerificationStatus.FAILED},
        {**verified, "title": "C"},
    ]))
    assert len(sends) == 2
    assert [send.arg["current_job"]["title"] for send in sends] == ["A", "C"]
    assert all(send.node == "analyze_verified_job" for send in sends)
    assert all(send.arg["verified_analyses"] == [] for send in sends)


def test_final_ranking_preserves_not_needed_status():
    job = {"url": "https://example.com/job", "match_score": 80,
           "verification_status": VerificationStatus.NOT_NEEDED}
    result = nodes.final_rank_jobs(make_state(ranked_jobs=[job]))
    assert result["final_ranked_jobs"][0]["verification_status"] == VerificationStatus.NOT_NEEDED


@pytest.mark.parametrize("analysis_type", [None, AnalysisType.VERIFIED])
@pytest.mark.parametrize("status_fields, expected_status", [
    ({}, VerificationStatus.UNVERIFIED),
    ({"verification_status": None}, VerificationStatus.UNVERIFIED),
    ({"verification_status": ""}, VerificationStatus.UNVERIFIED),
    ({"verification_status": " "}, VerificationStatus.UNVERIFIED),
    ({"verification_status": "unknown"}, VerificationStatus.UNVERIFIED),
    ({"verification_status": "approved"}, VerificationStatus.UNVERIFIED),
    ({"verification_status": "VERIFIED"}, VerificationStatus.UNVERIFIED),
    ({"verification_status": {}}, VerificationStatus.UNVERIFIED),
    ({"verification_status": True}, VerificationStatus.UNVERIFIED),
    ({"verification_status": VerificationStatus.NOT_NEEDED}, VerificationStatus.NOT_NEEDED),
    ({"verification_status": VerificationStatus.PENDING}, VerificationStatus.PENDING),
    ({"verification_status": VerificationStatus.FAILED}, VerificationStatus.FAILED),
])
def test_report_does_not_invent_verification_status(status_fields, expected_status, analysis_type):
    job = {
        "title": "A", "company": "Example", "location": "Remote",
        "confidence": "Medium", "recommendation": "Apply", "match_score": 80,
        **status_fields,
    }
    if analysis_type is not None:
        job["analysis_type"] = analysis_type
    report = nodes.generate_report(make_state(jobs=[job], selected_jobs=[job]))["final_report"]
    assert "Preliminary Match Score: 80" in report
    assert "Verified Match Score: Not available" in report
    assert "Verified Match Score: 80" not in report
    assert f"Verification Status: {expected_status}\n" in report


def test_report_accepts_only_explicit_verified_status_without_analysis_type():
    job = {
        "title": "A", "company": "Example", "location": "Remote",
        "confidence": "High", "recommendation": "Apply", "match_score": 90,
        "preliminary_match_score": 80,
        "verification_status": VerificationStatus.VERIFIED,
    }
    report = nodes.generate_report(make_state(jobs=[job], selected_jobs=[job]))["final_report"]
    assert "Verified Match Score: 90\n" in report
    assert "Preliminary Match Score: 80\n" in report
    assert "Verification Status: verified\n" in report


def test_extraction_returns_failure_when_both_providers_fail(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(web_search, "TavilyClient", Mock(side_effect=RuntimeError("unavailable")))
    http = Mock(side_effect=web_search.requests.Timeout("timeout"))
    monkeypatch.setattr(web_search.requests, "get", http)
    result = web_search.extract_job_description("https://example.com/job")
    http.assert_called_once()
    assert result["status"] == "failed"
    assert result["tavily_error"] == "unavailable"
    assert result["error"] == "timeout"
