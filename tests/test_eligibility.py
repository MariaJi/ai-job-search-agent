import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import nodes
from app.api_service import build_response
from app.eligibility import SearchConstraints, VerifiedConstraintsEvidence, assess_eligibility
from app.tools import web_search
from test_api import completed_state
from test_graph_empty_paths import job


def evidence(**facts):
    return {"facts": facts, "source_url": "https://example.com/job",
            "description_source": "direct_http", "observed_at": "2026-09-25T12:00:00+00:00"}


@pytest.mark.parametrize("constraints,facts,status", [
    ({"remote_required": True}, {"work_arrangement": "in_office"}, "contradicted"),
    ({"remote_required": True}, {"work_arrangement": "hybrid"}, "contradicted"),
    ({"remote_required": True}, {"work_arrangement": "remote"}, "compatible"),
    ({"remote_required": True}, {}, "unknown"),
    ({"country_codes": ["US"]}, {"country_codes": ["AU"], "countries_exhaustive": True}, "contradicted"),
    ({"country_codes": ["US"]}, {"country_codes": ["US", "CA"], "countries_exhaustive": True}, "compatible"),
    ({"country_codes": ["US"]}, {"country_codes": ["AU"], "countries_exhaustive": False}, "unknown"),
    ({"country_codes": ["US"]}, {"headquarters": "Australia"}, "unknown"),
    ({"geography": "Seattle"}, {}, "unknown"),
    ({"geography": "Seattle", "geography_scope": "subnational", "country_codes": ["US"]},
     {"country_codes": ["US"], "countries_exhaustive": True}, "unknown"),
    ({"recency_days": 7}, {"posting_date": "2026-09-07"}, "contradicted"),
    ({"recency_days": 7}, {"posting_age_days": 18}, "contradicted"),
    ({"recency_days": 7}, {"posting_date": "2026-09-18"}, "compatible"),
    ({"recency_days": 7}, {"posting_age_days": 7}, "compatible"),
    ({"recency_days": 7}, {"posting_date": "2026-10-01"}, "unknown"),
    ({"recency_days": 7}, {"posting_date": "invalid"}, "unknown"),
    ({"recency_days": 7}, {"posting_date": "2026-09-07", "posting_age_days": 2}, "unknown"),
    ({"recency_days": 7}, {"updated_date": "2026-09-25"}, "unknown"),
    ({}, {"posting_age_days": 18, "work_arrangement": "in_office"}, "unknown"),
])
def test_conservative_eligibility(constraints, facts, status):
    assert assess_eligibility(constraints, evidence(**facts))["status"] == status


@pytest.mark.parametrize("requested,permitted,status", [
    (["GB"], ["UK"], "compatible"),
    (["UK"], ["GB"], "compatible"),
    ([" gb "], ["uk"], "compatible"),
    (["US"], ["ZZ"], "unknown"),
    (["ZZ"], ["US"], "unknown"),
    (["US"], ["AU", "ZZ"], "unknown"),
    (["US"], ["US", "ZZ"], "unknown"),
    (["US", "ZZ"], ["AU"], "unknown"),
    (["US"], ["AU", None], "unknown"),
    (["US"], ["EU"], "unknown"),
    (["US"], ["AU"], "contradicted"),
    (["DE"], ["FR"], "contradicted"),
    (["US"], ["CA", "US"], "compatible"),
])
def test_country_normalization_and_supported_codes(requested, permitted, status):
    result = assess_eligibility({"country_codes": requested},
                                evidence(country_codes=permitted, countries_exhaustive=True))
    assert result["checks"]["geography"] == status
    assert result["status"] == status


@pytest.mark.parametrize("values", [None, "US", 42, {}, [None], [42], [True], [[]], [{}],
                                   [""], [" "], ["U"], ["US/AU"], ["U.S."], ["United States"]])
@pytest.mark.parametrize("side", ["requested", "permitted"])
def test_malformed_country_values_are_unknown(values, side):
    requested = values if side == "requested" else ["US"]
    permitted = values if side == "permitted" else ["AU"]
    result = assess_eligibility({"geography": "Requested location", "country_codes": requested},
                                evidence(country_codes=permitted, countries_exhaustive=True))
    assert result["checks"]["geography"] == "unknown"
    assert result["status"] == "unknown"


def test_unknown_requested_country_is_not_lost_when_remote_is_compatible():
    result = assess_eligibility({"remote_required": True, "country_codes": ["ZZ"]},
                                evidence(work_arrangement="remote", country_codes=["AU"],
                                         countries_exhaustive=True))
    assert result["status"] == "unknown"


def test_unknown_geography_does_not_hide_a_definite_remote_contradiction():
    result = assess_eligibility({"remote_required": True, "country_codes": ["US"]},
                                evidence(work_arrangement="in_office", country_codes=["ZZ"],
                                         countries_exhaustive=True))
    assert result["checks"]["geography"] == "unknown"
    assert result["status"] == "contradicted"


@pytest.mark.parametrize("explicit", [False, True])
def test_explicit_constraints_are_separate_from_retrieval_defaults(monkeypatch, explicit):
    constraints = SearchConstraints(remote_required=True, geography="United States",
                                    country_codes=["US"], recency_days=7 if explicit else None)
    model = Mock()
    model.invoke.return_value = nodes.SearchCriteria(
        role="Engineer", location="Remote", employment_type="", days_old=7, constraints=constraints)
    monkeypatch.setattr(nodes, "get_structured_model", Mock(return_value=model))
    request = "Find remote engineering roles in the US"
    if explicit:
        request += ", posted in the last 7 days"
    result = nodes.understand_search_request({"search_request": request})
    assert result["location"] == "Remote"
    assert result["days_old"] == 7
    assert result["search_constraints"] == constraints.model_dump()
    prompt = model.invoke.call_args.args[0]
    assert "even when location is Remote" in prompt
    assert "null when omitted" in prompt


@pytest.mark.parametrize("search_request,location,remote,geography,countries,scope", [
    ("Find remote Senior Software Engineer jobs.", "Remote", True, "", [], "unknown"),
    ("Find remote Senior Software Engineer jobs in the US.", "Remote", True, "US", ["US"], "country"),
    ("Find Senior Software Engineer jobs in the US.", "US", False, "US", ["US"], "country"),
])
def test_remote_geography_prompt_propagation_and_jooble_payload(
    monkeypatch, search_request, location, remote, geography, countries, scope
):
    # Mocked structured output tests the contract/prompt and downstream wiring,
    # not a live model's natural-language extraction accuracy.
    constraints = SearchConstraints(remote_required=remote, geography=geography,
                                    country_codes=countries, geography_scope=scope)
    model = Mock()
    model.invoke.return_value = nodes.SearchCriteria(
        role="Senior Software Engineer", location=location, employment_type="",
        days_old=7, constraints=constraints)
    monkeypatch.setattr(nodes, "get_structured_model", Mock(return_value=model))
    state = nodes.understand_search_request({"search_request": search_request})
    assert state["location"] == location
    assert state["search_constraints"] == constraints.model_dump()
    assert state["days_old"] == 7
    assert state["search_constraints"]["recency_days"] is None
    prompt = model.invoke.call_args.args[0]
    assert search_request in prompt
    assert "Remote takes precedence for retrieval location" in prompt
    assert 'geography="", geography_scope="unknown"' in prompt
    assert "Never default missing geography to US or worldwide" in prompt
    assert "remote does not mean worldwide eligibility" in prompt
    assert "remote_required=false" in prompt
    assert "null when omitted" in prompt

    from app.tools import job_search
    monkeypatch.setenv("JOOBLE_API_KEY", "synthetic-test-key")
    response = Mock()
    response.json.return_value = {"jobs": []}
    post = Mock(return_value=response)
    monkeypatch.setattr(job_search.requests, "post", post)
    nodes.search_jobs(state)
    post.assert_called_once()
    assert post.call_args.kwargs["json"] == {
        "keywords": "Senior Software Engineer", "location": location, "ResultOnPage": 10}
    response.raise_for_status.assert_called_once()


def test_remote_only_request_allows_country_restricted_remote_job():
    constraints = SearchConstraints(remote_required=True).model_dump()
    result = assess_eligibility(constraints, evidence(
        work_arrangement="remote", country_codes=["AU"], countries_exhaustive=True,
        posting_age_days=18))
    assert result == {"status": "compatible", "checks": {
        "remote": "compatible", "geography": "unknown", "recency": "unknown"}}


@pytest.mark.parametrize("facts,expected", [
    ({"posting_age_days": 18}, "Skip"),
    ({"work_arrangement": "in_office", "country_codes": ["AU"], "countries_exhaustive": True}, "Skip"),
    ({}, "Strong Apply"),
    ({"posting_age_days": 2, "work_arrangement": "remote", "country_codes": ["US"], "countries_exhaustive": True}, "Strong Apply"),
])
def test_final_gate_preserves_verified_scores_and_api_contract(facts, expected):
    state = completed_state()
    verified = {**state["final_ranked_jobs"][0], "job_id": "a" * 32,
                "updated_date": "2026-09-25", "verified_evidence": evidence(**facts)}
    state.update(search_constraints={"remote_required": True, "geography": "US",
                                    "country_codes": ["US"], "recency_days": 7},
                 ranked_jobs=[{**verified, "verification_status": "pending", "match_score": 80}],
                 verified_jobs=[verified], verified_analyses=[verified])
    state.update(nodes.final_rank_jobs(state))
    state.update(nodes.select_jobs(state))
    final = state["final_ranked_jobs"][0]
    assert final["recommendation"] == expected
    assert final["verification_status"] == "verified"
    assert final["preliminary_match_score"] == 80
    assert final["match_score"] == 90
    assert final["verified_evidence"] == verified["verified_evidence"]
    assert len(state["selected_jobs"]) == int(expected != "Skip")
    response = build_response(state)
    assert response.ranked_jobs[0].recommendation == ("Skip" if expected == "Skip" else "Apply")
    assert response.ranked_jobs[0].verified_match_score == 90
    assert response.ranked_jobs[0].source_urls.verified == verified["verified_url"]
    assert "eligibility" not in response.ranked_jobs[0].model_dump()


def test_stale_apply_is_blocked_in_selection_and_api():
    state = completed_state()
    state["final_ranked_jobs"][0]["eligibility"] = {"status": "contradicted"}
    assert nodes.select_jobs(state)["selected_jobs"] == []
    assert build_response(state).ranked_jobs[0].recommendation == "Skip"


def test_structured_metadata_stays_with_selected_description():
    first = {"@type": "JobPosting", "description": "", "datePosted": "2026-09-25"}
    second = {"@type": "JobPosting", "description": "Build APIs", "datePosted": "2026-09-07",
              "jobLocation": {"address": {"addressCountry": "AU"}},
              "hiringOrganization": {"address": "US headquarters"}, "dateModified": "2026-09-25"}
    html = '<script type="application/ld+json">' + json.dumps({"@graph": [first, second]}) + '</script>'
    result = web_search.parse_job_posting(html)
    assert result["content"] == "Build APIs"
    assert result["structured_metadata"] == {
        "datePosted": "2026-09-07", "jobLocation": second["jobLocation"]}


def test_verified_metadata_evidence_and_provenance_are_preserved(monkeypatch):
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    source = {"title": "Engineer", "url": "https://example.com/job", "raw_content": "Full description"}
    monkeypatch.setattr(nodes, "search_original_job", Mock(return_value=[source]))
    monkeypatch.setattr(nodes, "rank_job_sources", Mock(return_value=[source]))
    monkeypatch.setattr(nodes, "validate_extracted_job", Mock(return_value=SimpleNamespace(
        is_same_job=True, description_sufficient=True)))
    facts = VerifiedConstraintsEvidence(work_arrangement="in_office", country_codes=["AU"],
                                        countries_exhaustive=True, posting_age_days=18)
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", Mock(return_value=nodes.VerifiedJobMetadata(
        title="Engineer", company="Example", location="Sydney", eligibility_evidence=facts)))
    result = nodes.verify_job({"current_job": {**job(), "description": "Snippet"}})["verified_jobs"][0]
    assert result["verification_status"] == "verified"
    assert result["verified_evidence"]["facts"] == facts.model_dump()
    assert result["verified_evidence"]["source_url"] == source["url"]
    assert result["verified_evidence"]["description_source"] == "tavily_search_raw_content"
    assert result["verified_evidence"]["observed_at"]


def test_metadata_prompt_excludes_update_dates_and_headquarters(monkeypatch):
    model = Mock()
    monkeypatch.setattr(nodes, "get_structured_model", Mock(return_value=model))
    nodes.extract_verified_job_metadata({"title": "Engineer", "url": "https://example.com"},
                                       "Text", {"datePosted": "2026-09-07"})
    prompt = model.invoke.call_args.args[0]
    assert "Never use company headquarters" in prompt
    assert "Never use an updated/modified date" in prompt
    assert "2026-09-07" in prompt
