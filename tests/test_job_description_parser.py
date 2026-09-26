import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import nodes
from app.tools import web_search
from test_graph_empty_paths import job


POSTING = {"@type": "JobPosting", "description": "<p>Build APIs &amp; services.</p><p>Requires Python.</p>"}
TEXT = "Build APIs & services.\nRequires Python."


def script(data):
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>'


@pytest.mark.parametrize("data", [
    POSTING,
    [None, 42, {"@type": "Organization"}, POSTING],
    {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, POSTING]},
    {"wrapper": [{"nested": {"@graph": [[POSTING]]}}]},
    {**POSTING, "@type": ["Thing", "JobPosting"]},
])
def test_supported_jsonld_structures(data):
    assert web_search.parse_job_description(script(data)) == TEXT


@pytest.mark.parametrize("prefix", [
    script({"@type": "Organization", "description": "Not a job"}),
    '<script type="application/ld+json">{broken</script>',
    '<script type="application/ld+json"></script>',
    '<script type="application/ld+json">   </script>',
    script(None), script(42), script("unsupported"), script(True),
])
def test_skips_invalid_or_unrelated_scripts(prefix):
    assert web_search.parse_job_description(prefix + script(POSTING)) == TEXT


@pytest.mark.parametrize("invalid", [
    {"@type": "JobPosting"},
    *[{"@type": "JobPosting", "description": value}
      for value in (None, 42, False, [], {}, "", " \n\t ", "<p> &nbsp; </p><br>")],
])
@pytest.mark.parametrize("separate_scripts", [False, True])
def test_skips_unusable_descriptions(invalid, separate_scripts):
    html = script(invalid) + script(POSTING) if separate_scripts else script([invalid, POSTING])
    assert web_search.parse_job_description(html) == TEXT


@pytest.mark.parametrize("html", [
    '<div class="job-description">Build APIs. Requires Python.</div>',
    script({"@type": "WebPage", "description": "Not a job"}),
    script({"@type": ["Thing"], "description": "Not a job"}),
    script({"@type": None, "description": "Not a job"}),
])
def test_no_jobposting_returns_empty(html):
    assert web_search.parse_job_description(html) == ""


@pytest.mark.parametrize("separate_scripts", [False, True])
def test_first_usable_posting_is_not_merged(separate_scripts):
    second = {"@type": "JobPosting", "description": "Another job"}
    html = script(POSTING) + script(second) if separate_scripts else script([POSTING, second])
    assert web_search.parse_job_description(html) == TEXT


@pytest.mark.parametrize("same,sufficient", [(False, True), (True, False), (True, True)])
def test_recursive_http_evidence_requires_both_validation_checks(monkeypatch, same, sufficient):
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-test-only")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    source = {"title": "AI Engineer", "url": "https://example.com/job", "content": "Snippet"}
    monkeypatch.setattr(nodes, "search_original_job", Mock(return_value=[source]))
    monkeypatch.setattr(nodes, "evaluate_job_source_match", Mock(return_value=SimpleNamespace(
        is_same_job=True, confidence="High", reason="Synthetic")))
    client = Mock()
    client.extract.return_value = {"results": []}
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    get = Mock(return_value=Mock(status_code=200, text=script({"@graph": [POSTING]})))
    monkeypatch.setattr(web_search.requests, "get", get)
    validate = Mock(return_value=nodes.ExtractedJobValidation(
        is_same_job=same, description_sufficient=sufficient, confidence="High", reason="Synthetic"))
    monkeypatch.setattr(nodes, "validate_extracted_job", validate)
    metadata = Mock(return_value=SimpleNamespace(location="Remote", employment_type="Contract"))
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", metadata)
    original = {**job(), "description": "Original snippet", "description_complete": False,
                "preliminary_match_score": 91}
    result = nodes.verify_job({"current_job": original})["verified_jobs"][0]
    get.assert_called_once()
    validate.assert_called_once()
    assert validate.call_args.kwargs["extracted_description"] == TEXT
    assert metadata.call_count == int(same and sufficient)
    if same and sufficient:
        assert result["verification_status"] == "verified"
        assert result["description_complete"] is True
        assert result["description"] == TEXT
    else:
        assert result == {**original, "verification_status": "failed"}
        assert nodes.send_verified_jobs_for_analysis({"verified_jobs": [result]}) == "collect_verified_analyses"
