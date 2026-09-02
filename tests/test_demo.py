from unittest.mock import Mock
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api import BodyLimitMiddleware, create_app, get_workflow_runner
from app.api_models import JobSearchResponse


@pytest.mark.parametrize("enabled", [None, "false", "", "yes", "1"])
def test_demo_and_health_are_key_free_and_live_is_closed(monkeypatch, enabled):
    for name in ("OPENAI_API_KEY", "JOOBLE_API_KEY", "TAVILY_API_KEY", "ENABLE_LIVE_SEARCH", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    if enabled is not None:
        monkeypatch.setenv("ENABLE_LIVE_SEARCH", enabled)
    forbidden = Mock(side_effect=AssertionError("Provider must not initialize"))
    monkeypatch.setattr("langchain_openai.ChatOpenAI", forbidden)
    monkeypatch.setattr("tavily.TavilyClient", forbidden)
    app = create_app()
    app.dependency_overrides[get_workflow_runner] = forbidden
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/api/v1/demo")
        assert response.status_code == 200
        result = JobSearchResponse.model_validate(response.json())
        assert result.run_summary.returned_jobs == len(result.ranked_jobs)
        assert "synthetic" in result.run_summary.warnings[0]
        for job in result.ranked_jobs:
            if job.verification_status != "verified":
                assert job.verified_match_score is None
        assert client.get("/api/v1/demo").json() == response.json()
        assert client.post("/api/v1/job-search", content=b"not even multipart").status_code == 403
    forbidden.assert_not_called()


def test_keys_do_not_enable_paid_endpoint(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_SEARCH", raising=False)
    for name in ("OPENAI_API_KEY", "JOOBLE_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(name, "synthetic-test-value")
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/job-search").json()["error"]["code"] == "live_search_disabled"


def test_disabled_live_rejects_before_reading_any_upload():
    async def forbidden(*args):
        raise AssertionError("Must not read the upload or invoke the app")
    messages = []
    async def send(message):
        messages.append(message)
    asyncio.run(BodyLimitMiddleware(forbidden, live_enabled=False)(
        {"type": "http", "method": "POST", "path": "/api/v1/job-search"}, forbidden, send,
    ))
    assert messages[0]["status"] == 403


@pytest.mark.parametrize("message, status", [
    ("PRIVATE_RESUME_SENTINEL SECRET_SENTINEL", "failed"),
    ("quota PRIVATE_RESUME_SENTINEL SECRET_SENTINEL", "service_error"),
])
def test_verification_diagnostics_do_not_log_untrusted_details(monkeypatch, capsys, message, status):
    from app import nodes
    monkeypatch.setattr(nodes, "search_original_job", Mock(side_effect=RuntimeError(message)))
    result = nodes.verify_job({"current_job": {
        "title": "PRIVATE_TITLE_SENTINEL", "company": "Synthetic", "description_complete": False,
    }})
    assert result["verified_jobs"][0]["verification_status"] == status
    assert capsys.readouterr().out == "Verification unavailable; retaining preliminary results.\n"


def test_demo_uses_same_openapi_schema_and_explicit_local_cors(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    app = create_app()
    paths = app.openapi()["paths"]
    def schema(path, method):
        return paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema("/api/v1/demo", "get") == schema("/api/v1/job-search", "post")
    with TestClient(app) as client:
        allowed = client.get("/api/v1/demo", headers={"Origin": "http://localhost:5173"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-credentials" not in allowed.headers
        denied = client.get("/api/v1/demo", headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in denied.headers
