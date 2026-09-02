from copy import deepcopy

import pytest

from app.api_service import build_response
from test_api import completed_state


@pytest.mark.parametrize("status", [
    "source_not_found", "not_found", "not_attempted", "not_needed", "unverified",
    "pending", "failed", "service_error", "unknown", "", None, True, 1, [], {},
    "VERIFIED", " verified ", "missing",
])
@pytest.mark.parametrize("analysis_type", ["verified", "preliminary"])
@pytest.mark.parametrize("recommendation", ["Apply", "Strong Apply"])
def test_unverified_recommendations_always_require_review(status, analysis_type, recommendation):
    state = completed_state()
    job = state["final_ranked_jobs"][0]
    job.update(analysis_type=analysis_type, recommendation=recommendation)
    if status == "missing":
        job.pop("verification_status")
    else:
        job["verification_status"] = status
    before = deepcopy(state)
    assert build_response(state).ranked_jobs[0].recommendation == "Review original posting"
    assert state == before  # Internal matching decisions remain untouched.


@pytest.mark.parametrize("recommendation,expected", [
    ("Strong Apply", "Apply"), ("Apply", "Apply"), ("Maybe", "Maybe"), ("Skip", "Skip"),
    ("Definitely Apply now", "Review original posting"), (None, "Review original posting"),
    ({"action": "Apply"}, "Review original posting"),
])
def test_verified_recommendation_allowlist(recommendation, expected):
    state = completed_state()
    state["final_ranked_jobs"][0]["recommendation"] = recommendation
    assert build_response(state).ranked_jobs[0].recommendation == expected


def test_explicit_preliminary_analysis_cannot_promote_recommendation():
    state = completed_state()
    state["final_ranked_jobs"][0]["analysis_type"] = "preliminary"
    assert build_response(state).ranked_jobs[0].recommendation == "Review original posting"
