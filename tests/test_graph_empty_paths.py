from types import SimpleNamespace
import pytest

from app import nodes
from app.constants import VerificationStatus
from main import build_initial_state


class StructuredModel:
    def __init__(self, value):
        self.value = value

    def invoke(self, prompt):
        return self.value


def analysis(score_parts):
    values = {
        "technical_score": score_parts[0],
        "experience_score": score_parts[1],
        "role_specific_score": score_parts[2],
        "tools_platform_score": score_parts[3],
        "location_score": score_parts[4],
        "confidence": "Medium",
        "strengths": ["Python"],
        "missing_skills": [],
    }
    return SimpleNamespace(**values, model_dump=lambda: values)


def invoke_offline_graph(monkeypatch, raw_jobs, job_analysis=None, updates=False):
    models = {
        nodes.SearchCriteria: StructuredModel(
            SimpleNamespace(
                role="AI Engineer",
                location="Remote",
                employment_type="Full-time",
                days_old=7,
            )
        ),
        nodes.CandidateProfile: StructuredModel(
            SimpleNamespace(model_dump=lambda: {"skills": ["Python"]})
        ),
    }
    monkeypatch.setattr(nodes, "get_structured_model", lambda schema: models[schema])
    monkeypatch.setattr(
        nodes,
        "search_jooble_jobs",
        lambda **kwargs: {"jobs": raw_jobs},
    )
    if job_analysis is not None:
        monkeypatch.setattr(
            nodes, "score_job", lambda job, profile: job_analysis
        )

    from app.graph import graph

    state = build_initial_state("Find remote AI jobs", "Python")
    if updates:
        return list(graph.stream(state, stream_mode="updates"))
    return graph.invoke(state)


def job():
    return {
        "title": "AI Engineer",
        "company": "Example",
        "location": "Remote",
        "snippet": "Build AI systems",
        "link": "https://example.com/job",
        "source": "example",
        "updated": "",
    }


def test_graph_finalizes_when_no_jobs_are_returned(monkeypatch):
    result = invoke_offline_graph(monkeypatch, [])

    assert result["jobs"] == []
    assert result["final_ranked_jobs"] == []
    assert result["selected_jobs"] == []
    assert result["final_report"] == (
        "No jobs were found for the requested criteria."
    )


def test_graph_finalizes_when_no_verification_candidates(monkeypatch):
    result = invoke_offline_graph(
        monkeypatch, [job()], analysis((10, 10, 5, 3, 5))
    )

    assert result["verification_candidates"] == []
    assert len(result["final_ranked_jobs"]) == 1
    assert result["final_report"] == (
        "No job matches met the application threshold."
    )


@pytest.mark.parametrize("status", [
    VerificationStatus.NOT_FOUND, VerificationStatus.FAILED, VerificationStatus.SERVICE_ERROR,
])
def test_graph_finalizes_when_verification_does_not_succeed(monkeypatch, status):
    def search(**kwargs):
        if status == VerificationStatus.NOT_FOUND:
            return []
        if status == VerificationStatus.SERVICE_ERROR:
            raise RuntimeError("quota exhausted")
        raise RuntimeError("unavailable")

    monkeypatch.setattr(nodes, "search_original_job", search)
    result = invoke_offline_graph(
        monkeypatch, [job()], analysis((35, 20, 15, 8, 5))
    )

    assert result["verified_analyses"] == []
    assert result["final_ranked_jobs"][0]["verification_status"] == (
        status
    )
    assert "Preliminary Match Score: 83" in result["final_report"]
    assert "Verified Match Score: Not available" in result["final_report"]


def test_zero_verification_budget_keeps_preliminary_matches(monkeypatch):
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "0")
    result = invoke_offline_graph(monkeypatch, [job()], analysis((35, 20, 15, 8, 5)))
    assert result["verification_candidates"] == []
    assert result["selected_jobs"][0]["verification_status"] == VerificationStatus.NOT_ATTEMPTED
    assert "Preliminary Match Score: 83" in result["final_report"]


def test_parallel_reducers_collect_each_job_once_with_mixed_verification(monkeypatch):
    from app.constants import AnalysisType

    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "3")
    jobs = [{**job(), "title": title, "link": f"https://example.com/{title}"}
            for title in ("A", "B", "missing")]
    monkeypatch.setattr(nodes, "score_job", lambda job, profile:
                        analysis((38, 23, 18, 9, 5)) if job["description_complete"]
                        else analysis((35, 20, 15, 8, 5)))
    monkeypatch.setattr(nodes, "search_original_job", lambda title, company:
                        [] if title == "missing" else [{"title": title, "url": f"https://example.com/{title}"}])
    monkeypatch.setattr(nodes, "rank_job_sources", lambda job, search_results: search_results)
    monkeypatch.setattr(nodes, "extract_job_description", lambda url:
                        {"status": "success", "content": "Full description", "source": "mock"})
    monkeypatch.setattr(nodes, "validate_extracted_job", lambda **kwargs:
                        SimpleNamespace(is_same_job=True))
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", lambda **kwargs:
                        SimpleNamespace(location="Remote", employment_type="Full-time"))

    events = invoke_offline_graph(monkeypatch, jobs, updates=True)
    by_node = {}
    for event in events:
        for name, value in event.items():
            by_node.setdefault(name, []).append(value)

    assert len(by_node["analyze_job"]) == 3
    assert len(by_node["verify_job"]) == 3
    assert len(by_node["analyze_verified_job"]) == 2
    for name in ("rank_jobs", "collect_verified_jobs", "collect_verified_analyses",
                 "final_rank_jobs", "select_jobs", "generate_report"):
        assert len(by_node[name]) == 1, name
    assert len(by_node["rank_jobs"][0]["ranked_jobs"]) == 3
    final_jobs = by_node["final_rank_jobs"][0]["final_ranked_jobs"]
    assert len(final_jobs) == 3
    assert {job["title"] for job in final_jobs} == {"A", "B", "missing"}
    assert [job["match_score"] for job in final_jobs] == [93, 93, 83]
    assert [job["analysis_type"] for job in final_jobs] == [
        AnalysisType.VERIFIED, AnalysisType.VERIFIED, AnalysisType.PRELIMINARY,
    ]
    assert all(job["preliminary_match_score"] == 83 for job in final_jobs)
