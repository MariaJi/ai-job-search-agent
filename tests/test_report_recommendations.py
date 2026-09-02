from copy import deepcopy

import pytest

from app.nodes import generate_report
from app.api_service import build_response
from test_api import completed_state


@pytest.mark.parametrize("status", ["verified", "not_attempted", "source_not_found", "not_found", "not_needed", "unverified", "pending", "failed", "service_error", "unknown", "unsupported", "", None, True, 1, [], {}, "VERIFIED", " verified ", "missing"])
@pytest.mark.parametrize("analysis_type", ["verified", "preliminary"])
@pytest.mark.parametrize("recommendation", ["Apply", "Strong Apply", "Maybe", "Skip", "Apply now!", None, {}])
def test_report_and_api_share_evidence_gate(status, analysis_type, recommendation):
    state = completed_state()
    item = state["final_ranked_jobs"][0]
    item.update(verification_status=status, analysis_type=analysis_type, recommendation=recommendation)
    if status == "missing":
        item.pop("verification_status")
    state["selected_jobs"] = [item]
    before = deepcopy(state)
    expected = "Review original posting"
    if status == "verified" and analysis_type == "verified":
        if recommendation in ("Apply", "Strong Apply"):
            expected = "Apply"
        elif recommendation in ("Maybe", "Skip"):
            expected = recommendation
    report = generate_report(state)["final_report"]
    assert f"Recommendation: {expected}\n" in report
    assert build_response(state).ranked_jobs[0].recommendation == expected
    assert state == before
