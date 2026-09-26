import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import nodes
from app.tools import web_search
from test_graph_empty_paths import job


@pytest.mark.parametrize("raw,extracted,http,same,sufficient,expected_source,counts", [
    ("full", "full", "full", True, True, "tavily_search_raw_content", (0, 0, 1)),
    (None, "full", "full", True, True, "tavily_extract", (1, 0, 1)),
    ("short", "full", "full", True, True, "tavily_extract", (1, 0, 2)),
    (None, "error", "full", True, True, "direct_http", (1, 1, 1)),
    (None, "short", "full", True, True, "direct_http", (1, 1, 2)),
    (None, "", "", True, True, None, (1, 1, 0)),
    ("full", "full", "full", False, True, None, (1, 1, 3)),
    ("short", "short", "short", True, True, None, (1, 1, 3)),
    ("full", "full", "full", True, False, None, (1, 1, 3)),
])
def test_description_evidence_chain(monkeypatch, capsys, raw, extracted, http,
                                    same, sufficient, expected_source, counts):
    monkeypatch.setenv("TAVILY_API_KEY", "SECRET_KEY")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    texts = {"full": "PRIVATE_DESCRIPTION: Build Python services. Requires Python and API experience.",
             "short": "PRIVATE_DESCRIPTION: Engineer wanted.", "": "", None: None}
    client = Mock()
    source = {"title": "AI Engineer", "url": "https://example.com/PRIVATE_URL",
              "content": "PRIVATE_SNIPPET: identity evidence only", "raw_content": texts[raw]}
    client.search.return_value = {"results": [source]}
    if extracted == "error":
        client.extract.side_effect = RuntimeError("PRIVATE_EXCEPTION")
    else:
        client.extract.return_value = {"results": [{"raw_content": texts[extracted]}]}
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    html = '<script type="application/ld+json">' + json.dumps(
        {"@type": "JobPosting", "description": texts[http]}) + '</script>'
    get = Mock(return_value=Mock(status_code=200, text=html))
    monkeypatch.setattr(web_search.requests, "get", get)
    monkeypatch.setattr(nodes, "evaluate_job_source_match", Mock(return_value=SimpleNamespace(
        is_same_job=True, confidence="High", reason="PRIVATE_REASON")))

    def validate(**kwargs):
        return nodes.ExtractedJobValidation(
            is_same_job=same,
            description_sufficient=sufficient and kwargs["extracted_description"] == texts["full"],
            confidence="High", reason="PRIVATE_REASON")

    validator = Mock(side_effect=validate)
    monkeypatch.setattr(nodes, "validate_extracted_job", validator)
    metadata = Mock(return_value=SimpleNamespace(location="Remote", employment_type="Contract"))
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", metadata)
    original = {**job(), "description": "PRIVATE_ORIGINAL", "description_complete": False,
                "match_score": 91, "preliminary_match_score": 91}
    result = nodes.verify_job({"current_job": original})["verified_jobs"][0]

    assert client.search.call_args.kwargs["include_raw_content"] is True
    assert (client.extract.call_count, get.call_count, validator.call_count) == counts
    assert metadata.call_count == int(expected_source is not None)
    assert result["description_complete"] is (expected_source is not None)
    assert result["preliminary_match_score"] == 91
    if expected_source:
        assert result["verification_status"] == "verified"
        assert result["description_source"] == expected_source
        assert result["description"] == texts["full"]
    else:
        assert result == {**original, "verification_status": "failed"}
        assert nodes.send_verified_jobs_for_analysis({"verified_jobs": [result]}) == "collect_verified_analyses"
    for call in validator.call_args_list:
        assert call.kwargs["extracted_description"] != source["content"]
    output = capsys.readouterr().out
    assert "PRIVATE_" not in output
    assert "SECRET_KEY" not in output
    assert "https://" not in output


def test_validation_requires_explicit_sufficiency_and_instructs_model(monkeypatch):
    with pytest.raises(ValueError):
        nodes.ExtractedJobValidation(is_same_job=True, confidence="High", reason="match")
    model = Mock()
    monkeypatch.setattr(nodes, "get_structured_model", Mock(return_value=model))
    nodes.validate_extracted_job({**job(), "description": "snippet"},
                                 {"title": "Engineer", "url": "https://example.com"}, "text")
    prompt = model.invoke.call_args.args[0]
    assert "SAME specific job" in prompt
    assert "description_sufficient" in prompt
    assert "responsibilities and requirements" in prompt
    assert "Length alone does not establish sufficiency" in prompt
