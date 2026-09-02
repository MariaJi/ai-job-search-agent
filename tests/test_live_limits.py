from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from app import nodes
from app.api_service import ProviderConfigurationError, run_workflow
from app.graph import fan_out_jobs
from app.live_config import max_search_jobs, openai_max_retries
from test_graph_empty_paths import analysis, invoke_offline_graph, job


@pytest.mark.parametrize("limit", [1, 3, 10])
def test_requested_and_returned_jobs_are_capped(monkeypatch, limit):
    monkeypatch.setenv("MAX_SEARCH_JOBS", str(limit))
    search = Mock(return_value={"jobs": [job() for _ in range(25)]})
    monkeypatch.setattr(nodes, "search_jooble_jobs", search)
    state = nodes.search_jobs({"role": "Engineer", "location": "Remote", "days_old": 7})
    search.assert_called_once_with(keywords="Engineer", location="Remote", results_per_page=limit)
    assert len(state["jobs"]) == limit
    assert len(fan_out_jobs({"jobs": [job()] * 25, "candidate_profile": {}})) == limit


@pytest.mark.parametrize("limit", [1, 3, 10])
@pytest.mark.parametrize("count", [0, 25])
def test_graph_analysis_count_and_empty_finalization(monkeypatch, limit, count):
    monkeypatch.setenv("MAX_SEARCH_JOBS", str(limit))
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "0")
    scorer = Mock(return_value=analysis((35, 20, 15, 8, 5)))
    monkeypatch.setattr(nodes, "score_job", scorer)
    result = invoke_offline_graph(monkeypatch, [job() for _ in range(count)])
    assert scorer.call_count == min(count, limit)
    assert len(result["analyses"]) == min(count, limit)
    assert len(result["jobs"]) == min(count, limit)
    assert result["final_report"]


@pytest.mark.parametrize("name,value", [
    ("MAX_SEARCH_JOBS", value) for value in ("", " ", "bad", "0", "-1", "11", "3.0", "1e1", "SECRET_SENTINEL")
] + [("OPENAI_MAX_RETRIES", value) for value in ("", "bad", "-1", "3", "1.0")])
def test_invalid_configuration_stops_before_providers(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    factory = Mock(side_effect=AssertionError("No provider may initialize"))
    monkeypatch.setattr(nodes, "get_structured_model", factory)
    with pytest.raises(ValueError) as error:
        nodes.understand_search_request({"search_request": "Synthetic search"})
    assert value == "" or "SECRET_SENTINEL" not in str(error.value)
    with pytest.raises(ProviderConfigurationError):
        run_workflow("Synthetic search", "Synthetic resume")
    factory.assert_not_called()


def test_missing_settings_preserve_defaults(monkeypatch):
    monkeypatch.delenv("MAX_SEARCH_JOBS", raising=False)
    monkeypatch.delenv("OPENAI_MAX_RETRIES", raising=False)
    assert max_search_jobs() == 10
    assert openai_max_retries() == 2


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_retries_configures_unchanged_model(monkeypatch, retries):
    monkeypatch.setenv("OPENAI_MAX_RETRIES", str(retries))
    constructor = Mock()
    monkeypatch.setattr(nodes, "ChatOpenAI", constructor)
    nodes.get_model.cache_clear()
    try:
        nodes.get_model()
        constructor.assert_called_once_with(model="gpt-4o-mini", temperature=0, max_retries=retries)
    finally:
        nodes.get_model.cache_clear()


def test_actual_jooble_payload(monkeypatch):
    from app.tools import job_search
    monkeypatch.setenv("MAX_SEARCH_JOBS", "3")
    monkeypatch.setenv("JOOBLE_API_KEY", "synthetic-test-only")
    response = Mock()
    response.json.return_value = {"jobs": [job()] * 30}
    post = Mock(return_value=response)
    monkeypatch.setattr(job_search.requests, "post", post)
    result = nodes.search_jobs({"role": "Engineer", "location": "Remote", "days_old": 7})
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["ResultOnPage"] == 3
    assert len(result["jobs"]) == 3


@pytest.mark.parametrize("limit", [1, 5, 20])
@pytest.mark.parametrize("source_search", [False, True])
def test_tavily_truncates_before_processing(monkeypatch, limit, source_search):
    from app.tools import web_search
    monkeypatch.setenv("TAVILY_MAX_RESULTS", str(limit))
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-test-only")
    item = {"title": "Engineer", "url": "https://example.com/jobs/1", "content": "Synthetic"}
    # Any processing of entries beyond the cap raises, rather than merely adding work.
    client = Mock()
    client.search.return_value = {"results": [item] * limit + [None] * 30}
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    if source_search:
        results = web_search.search_job_on_source("Engineer", "Example", "https://example.com/jobs")
    else:
        results = web_search.search_original_job("Engineer", "Example")
    assert len(results) == limit
    assert client.search.call_count == 1
    assert client.search.call_args.kwargs["max_results"] == limit


@pytest.mark.parametrize("value", ["", " ", "bad", "0", "-1", "21", "1.5", "SECRET_SENTINEL"])
def test_invalid_tavily_limits_stop_before_any_provider(monkeypatch, value):
    from app.tools import web_search
    monkeypatch.setenv("TAVILY_MAX_RESULTS", value)
    constructor = Mock(side_effect=AssertionError("No provider construction"))
    model = Mock(side_effect=AssertionError("No model call"))
    monkeypatch.setattr(web_search, "TavilyClient", constructor)
    monkeypatch.setattr(nodes, "get_structured_model", model)
    for operation in (
        lambda: web_search.search_original_job("Engineer", "Example"),
        lambda: web_search.search_job_on_source("Engineer", "Example", "https://example.com"),
        lambda: nodes.understand_search_request({"search_request": "Synthetic"}),
    ):
        with pytest.raises(ValueError) as error:
            operation()
        assert "SECRET_SENTINEL" not in str(error.value)
    with pytest.raises(ProviderConfigurationError):
        run_workflow("Synthetic", "Synthetic")
    constructor.assert_not_called()
    model.assert_not_called()


@pytest.mark.parametrize("valid", [False, True])
def test_one_source_bounds_comparison_extraction_validation_and_fallback(monkeypatch, valid):
    from app.tools import web_search
    monkeypatch.setenv("MAX_SEARCH_JOBS", "3")
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "1")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-test-only")
    client = Mock()
    client.search.return_value = {"results": [
        {"title": "Engineer", "url": f"https://example.com/{i}", "content": "Synthetic"}
        for i in range(30)
    ]}
    client.extract.return_value = {"results": []}  # Exercise direct HTTP fallback too.
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    http = Mock()
    http.text = "Synthetic HTML"
    get = Mock(return_value=http)
    monkeypatch.setattr(web_search.requests, "get", get)
    monkeypatch.setattr(web_search, "parse_job_description", Mock(return_value="Synthetic description"))
    compare = Mock(return_value=SimpleNamespace(is_same_job=True, confidence="High", reason="Synthetic"))
    validate = Mock(return_value=SimpleNamespace(is_same_job=valid))
    metadata = Mock(return_value=SimpleNamespace(location="Remote", employment_type="Full-time"))
    score = Mock(return_value=analysis((35, 20, 15, 8, 5)))
    monkeypatch.setattr(nodes, "evaluate_job_source_match", compare)
    monkeypatch.setattr(nodes, "validate_extracted_job", validate)
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", metadata)
    monkeypatch.setattr(nodes, "score_job", score)
    result = invoke_offline_graph(monkeypatch, [job()] * 30)
    assert len(result["analyses"]) == 3
    assert len(result["verification_candidates"]) == 1
    assert client.search.call_count == client.extract.call_count == 1
    assert compare.call_count == validate.call_count == get.call_count == 1
    assert metadata.call_count == int(valid)
    assert score.call_count == 3 + int(valid)
    assert result["final_report"]


def test_verification_defends_against_oversized_helper_output(monkeypatch):
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    sources = [{"url": f"https://example.com/{i}"} for i in range(20)]
    monkeypatch.setattr(nodes, "search_original_job", Mock(return_value=sources))
    rank = Mock(return_value=sources)
    extract = Mock(return_value={"status": "failed"})
    monkeypatch.setattr(nodes, "rank_job_sources", rank)
    monkeypatch.setattr(nodes, "extract_job_description", extract)
    nodes.verify_job({"current_job": {"title": "Engineer", "company": "Example", "description_complete": False}})
    assert len(rank.call_args.kwargs["search_results"]) == 1
    assert extract.call_count == 1
