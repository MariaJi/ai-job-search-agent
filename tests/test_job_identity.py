from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import nodes
from app.api_service import build_response
from test_graph_empty_paths import analysis, invoke_offline_graph, job
from test_reliability import make_state


@pytest.mark.parametrize("url", [None, "", "https://example.com/shared"])
def test_identity_lifecycle_with_colliding_postings(monkeypatch, url):
    monkeypatch.setenv("MAX_SEARCH_JOBS", "3")
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "1")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    raw = [dict(job(), location=location) for location in ("Seattle", "Boston", "Austin")]
    for item in raw:
        item.pop("link")
        if url is not None:
            item["link"] = url
    monkeypatch.setattr(nodes, "score_job", Mock(return_value=analysis((35, 20, 15, 8, 5))))
    monkeypatch.setattr(nodes, "search_original_job", Mock(return_value=[{"url": "https://example.com/source"}]))
    monkeypatch.setattr(nodes, "rank_job_sources", lambda **kwargs: kwargs["search_results"])
    monkeypatch.setattr(nodes, "extract_job_description", Mock(return_value={"status": "success", "content": "Synthetic", "source": "test"}))
    monkeypatch.setattr(nodes, "validate_extracted_job", Mock(return_value=SimpleNamespace(is_same_job=True)))
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", Mock(return_value=SimpleNamespace(location="", employment_type="Full-time")))
    state = invoke_offline_graph(monkeypatch, raw)
    ids = [item["job_id"] for item in state["jobs"]]
    assert len(set(ids)) == 3
    for field in ("analyses", "ranked_jobs", "final_ranked_jobs", "selected_jobs"):
        assert [item["job_id"] for item in state[field]] == ids
    for field in ("verification_candidates", "verified_jobs", "verified_analyses"):
        assert [item["job_id"] for item in state[field]] == ids[:1]
    assert [item["location"] for item in state["final_ranked_jobs"]] == ["Seattle", "Boston", "Austin"]
    assert [item["analysis_type"] for item in state["final_ranked_jobs"]] == ["verified", "preliminary", "preliminary"]
    state["candidate_profile"] = {"summary": "Synthetic profile"}
    response = build_response(state)
    assert response.run_summary.verification_attempted == response.run_summary.verified_jobs == 1
    assert response.run_summary.jobs_analyzed == response.run_summary.returned_jobs == 3
    assert response.run_summary.preliminary_jobs == 2
    assert "job_id" not in response.model_dump_json()
    assert nodes.score_job.call_count == 4


@pytest.mark.parametrize("bad_id", [None, "", " ", "legacy", 1, True, [], {}, "A" * 32])
@pytest.mark.parametrize("side", ["preliminary", "verified", "both", "missing"])
def test_bad_or_missing_identity_cannot_promote(bad_id, side):
    original = {"job_id": uuid4().hex, "title": "Engineer", "company": "Example", "match_score": 83}
    verified = dict(original, verification_status="verified", match_score=93)
    if side in ("preliminary", "both"):
        original["job_id"] = bad_id
    if side in ("verified", "both"):
        verified["job_id"] = bad_id
    if side == "missing":
        original.pop("job_id")
        verified.pop("job_id")
    state = make_state(ranked_jobs=[original], verified_jobs=[verified], verified_analyses=[verified])
    before = deepcopy(state)
    final = nodes.final_rank_jobs(state)["final_ranked_jobs"][0]
    assert final["analysis_type"] == "preliminary"
    assert final["match_score"] == 83
    assert state == before


@pytest.mark.parametrize("duplicate_side", ["ranked_jobs", "verified_analyses"])
def test_ambiguous_ids_fail_conservatively(duplicate_side):
    item = {"job_id": uuid4().hex, "match_score": 80, "verification_status": "verified"}
    state = make_state(ranked_jobs=[item], verified_analyses=[item], verified_jobs=[item])
    state[duplicate_side] = [item, dict(item)]
    assert all(j["analysis_type"] == "preliminary" for j in nodes.final_rank_jobs(state)["final_ranked_jobs"])


def test_final_sort_preserves_score_order_and_ties():
    jobs = [{"job_id": uuid4().hex, "match_score": score} for score in (90, 80, 80)]
    verified = dict(jobs[2], match_score=95, verification_status="verified")
    final = nodes.final_rank_jobs(make_state(ranked_jobs=jobs, verified_analyses=[verified]))["final_ranked_jobs"]
    assert [j["job_id"] for j in final] == [jobs[i]["job_id"] for i in (2, 0, 1)]
