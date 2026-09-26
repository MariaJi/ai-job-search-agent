from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import nodes
from app.tools import web_search
from test_graph_empty_paths import job


@pytest.mark.parametrize("outcome,status,reason", [
    ("success", "verified", "success"),
    ("no_results", "not_found", "no_search_results"),
    ("no_match", "not_found", "no_matching_sources"),
    ("empty", "failed", "extraction_failed"),
    ("rejected", "failed", "validation_rejected"),
    ("metadata_error", "failed", "metadata_failed"),
])
def test_verification_stage_diagnostics(monkeypatch, capsys, outcome, status, reason):
    monkeypatch.setenv("TAVILY_API_KEY", "SECRET_KEY_SENTINEL")
    monkeypatch.setenv("TAVILY_MAX_RESULTS", "1")
    monkeypatch.setenv("MAX_VERIFICATION_JOBS", "1")
    source = {"title": "AI Engineer", "url": "https://example.com/PRIVATE_URL",
              "content": "PRIVATE_SNIPPET"}
    client = Mock()
    client.search.return_value = {"results": [] if outcome == "no_results" else [source, source]}
    client.extract.return_value = {"results": [{"raw_content": "" if outcome == "empty" else "PRIVATE_DESCRIPTION"}]}
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    response = Mock(status_code=200, text="<html>No description</html>")
    monkeypatch.setattr(web_search.requests, "get", Mock(return_value=response))
    monkeypatch.setattr(nodes, "evaluate_job_source_match", Mock(return_value=SimpleNamespace(
        is_same_job=outcome != "no_match", confidence="High", reason="PRIVATE_REASON")))
    monkeypatch.setattr(nodes, "validate_extracted_job", Mock(return_value=SimpleNamespace(
        is_same_job=outcome != "rejected", description_sufficient=True, confidence="Medium", reason="PRIVATE_REASON")))
    metadata = Mock(return_value=SimpleNamespace(location="Remote", employment_type="Contract"))
    if outcome == "metadata_error":
        metadata.side_effect = RuntimeError("PRIVATE_EXCEPTION")
    monkeypatch.setattr(nodes, "extract_verified_job_metadata", metadata)
    current = {**job(), "verification_priority": "High", "preliminary_match_score": 91,
               "match_score": 91, "description": "PRIVATE_ORIGINAL"}
    selected = nodes.select_verification_candidates({"ranked_jobs": [current]})
    result = nodes.verify_job({"current_job": selected["verification_candidates"][0]})
    assert result["verified_jobs"][0]["verification_status"] == status
    output = capsys.readouterr().out
    assert "Verification selection: limit=1 selected=1" in output
    assert "preliminary_score=91 priority=High" in output
    assert "source_limit=1" in output
    assert f"status={status} reason={reason}" in output
    assert "PRIVATE_" not in output
    assert "SECRET_KEY" not in output
    assert "https://" not in output
    if outcome == "no_results":
        assert "completed returned=0 considered=0" in output
    else:
        assert "completed returned=2 considered=1" in output
        assert f"source=1 is_same_job={outcome != 'no_match'} confidence=High" in output
        assert f"accepted={int(outcome != 'no_match')}" in output
        assert f"attempt_order={[] if outcome == 'no_match' else [1]}" in output
        assert f"decision={'rejected' if outcome == 'no_match' else 'accepted'}" in output
    if outcome == "empty":
        assert "outcome=empty usable=False characters=0" in output
        assert "fallback_attempted=True" in output
        assert "http_status=200" in output
    if outcome in ("success", "rejected", "metadata_error"):
        assert "stage=tavily_extract outcome=success usable=True characters=19" in output
        assert "fallback_attempted=False" in output
        assert f"source=1 is_same_job={outcome != 'rejected'} confidence=Medium" in output
    if outcome == "success":
        assert "Verification metadata: completed" in output
        assert "location_populated=True employment_type_populated=True" in output
    if outcome == "metadata_error":
        assert "stage=metadata class=RuntimeError" in output


def test_extraction_error_diagnostics_hide_exception_details(monkeypatch, capsys):
    monkeypatch.setenv("TAVILY_API_KEY", "SECRET_KEY")
    client = Mock()
    client.extract.side_effect = RuntimeError("PRIVATE_TAVILY_ERROR")
    monkeypatch.setattr(web_search, "TavilyClient", Mock(return_value=client))
    monkeypatch.setattr(web_search.requests, "get", Mock(
        side_effect=web_search.requests.Timeout("PRIVATE_HTTP_ERROR")))
    result = web_search.extract_job_description("https://example.com/PRIVATE_URL")
    assert result["status"] == "failed"
    output = capsys.readouterr().out
    assert "stage=tavily_extract outcome=error class=RuntimeError" in output
    assert "fallback_attempted=True" in output
    assert "stage=direct_http outcome=error class=Timeout" in output
    assert "PRIVATE_" not in output
    assert "SECRET_KEY" not in output
