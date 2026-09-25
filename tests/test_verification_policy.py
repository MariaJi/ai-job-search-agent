from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import nodes
from app.api_service import build_response
from test_graph_empty_paths import analysis, job


@pytest.mark.parametrize("outcome", ["verified", "not_found", "failed", "service_error"])
def test_jooble_snippet_verification_and_rescoring(monkeypatch, outcome):
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "1")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    def jooble_jobs(**kwargs):
        return {"jobs": [job()]}

    monkeypatch.setattr(nodes, "search_jooble_jobs", jooble_jobs)
    normalized = nodes.search_jobs({"role": "AI Engineer", "location": "Remote",
                                     "employment_type": "Full-time", "days_old": 7})["jobs"][0]
    assert normalized["description_complete"] is False
    assert normalized["description_source"] == "jooble_snippet"
    score = Mock(side_effect=[analysis((35, 20, 15, 8, 5)), analysis((38, 23, 18, 9, 5))])
    monkeypatch.setattr(nodes, "score_job", score)
    source = {"title": "AI Engineer", "url": "https://example.com/verified"}
    search = Mock(return_value=[] if outcome == "not_found" else [source])
    if outcome == "service_error":
        search.side_effect = RuntimeError("quota exhausted")
    monkeypatch.setattr(nodes, "search_original_job", search)
    monkeypatch.setattr(nodes, "rank_job_sources", lambda **kwargs: kwargs["search_results"])
    extract = Mock(return_value={"status": "success", "content": "Verified full description", "source": "test"})
    monkeypatch.setattr(nodes, "extract_job_description", extract)
    validate = Mock(return_value=SimpleNamespace(is_same_job=outcome == "verified"))
    monkeypatch.setattr(nodes, "validate_extracted_job", validate)
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", Mock(return_value=SimpleNamespace(location="Remote", employment_type="Full-time")))

    # Start at preliminary analysis and run the existing graph nodes/routing.
    state = {"jobs": [normalized], "candidate_profile": {"summary": "Python"},
             "verified_jobs": [], "verified_analyses": [], "role": "AI Engineer",
             "location": "Remote", "employment_type": "Full-time", "days_old": 7}
    state.update(nodes.analyze_job({**state, "current_job": normalized}))
    state.update(nodes.rank_jobs(state))
    state.update(nodes.select_verification_candidates(state))
    assert state["verification_candidates"] == state["ranked_jobs"]
    assert state["verification_candidates"][0]["description_complete"] is False
    for dispatch in nodes.send_verification_jobs(state):
        state["verified_jobs"].extend(nodes.verify_job(dispatch.arg)["verified_jobs"])
    dispatches = nodes.send_verified_jobs_for_analysis(state)
    if isinstance(dispatches, list):
        for dispatch in dispatches:
            state["verified_analyses"].extend(nodes.analyze_verified_job(dispatch.arg)["verified_analyses"])
    state.update(nodes.final_rank_jobs(state))
    state.update(nodes.select_jobs(state))

    search.assert_called_once()
    final = state["final_ranked_jobs"][0]
    assert final["verification_status"] == outcome
    assert final["preliminary_match_score"] == 83
    assert final["match_score"] == (93 if outcome == "verified" else 83)
    assert final["description_complete"] is (outcome == "verified")
    assert score.call_count == (2 if outcome == "verified" else 1)
    assert score.call_args_list[0].args[0]["description_complete"] is False
    assert len(state["verified_jobs"]) == 1
    assert len(state["selected_jobs"]) == int(outcome == "verified")
    if outcome in ("verified", "failed"):
        extract.assert_called_once()
        validate.assert_called_once()
    if outcome == "verified":
        assert score.call_args.args[0]["description"] == "Verified full description"
        assert score.call_args.args[0]["description_complete"] is True
    response = build_response(state)
    assert response.ranked_jobs[0].recommendation == ("Apply" if outcome == "verified" else "Review original posting")


@pytest.mark.parametrize("parts,confidence,expected", [
    ((35, 20, 15, 10, 5), "Medium", "High"),
    ((25, 0, 15, 0, 0), "Medium", "High"),
    ((20, 15, 10, 10, 5), "Medium", "Medium"),
    ((0, 20, 0, 0, 0), "Medium", "Medium"),
    ((0, 0, 0, 0, 0), "Low", "Medium"),
    ((10, 10, 5, 3, 5), "Medium", "Low"),
])
def test_snippet_verification_priority_rules(parts, confidence, expected):
    fit = analysis(parts)
    fit.confidence = confidence
    assert nodes.get_verification_priority({"description_complete": False}, fit, sum(parts)) == expected


@pytest.mark.parametrize("limit", [0, 1, 2, 10])
def test_candidate_limit_preserves_ranked_order_and_priority_eligibility(monkeypatch, limit):
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", str(limit))
    jobs = [
        {"verification_priority": priority, "description_complete": False,
         "needs_verification": True, "match_score": 95 - index}
        for index, priority in enumerate(["Low", "Medium", "High", "High", "Low"])
    ]
    assert nodes.select_verification_candidates({"ranked_jobs": jobs})["verification_candidates"] == jobs[1:4][:limit]
