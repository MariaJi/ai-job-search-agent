import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api_models import JobSearchResponse
from public_demo import app as service
from scripts.build_demo_release import RELEASE_FILES, build_release


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    for key in ("OPENAI_API_KEY", "JOOBLE_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with TestClient(service.create_app(), raise_server_exceptions=False) as client:
        yield client


def test_schema_and_synthetic_response(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/api/v1/demo")
    assert response.status_code == 200
    result = JobSearchResponse.model_validate(response.json())
    assert response.json() == json.loads(service.FIXTURE.read_text(encoding="utf-8"))
    assert set(response.json()) == {"criteria", "candidate_profile", "ranked_jobs", "run_summary"}
    assert result.run_summary.returned_jobs == len(result.ranked_jobs)
    assert "synthetic" in " ".join(result.run_summary.warnings).lower()
    for job in result.ranked_jobs:
        for url in job.source_urls.model_dump().values():
            if url:
                assert urlsplit(url).hostname == "example.com"
        if job.verification_status != "verified":
            assert job.verified_match_score is None
    assert "resume_text" not in response.text
    assert "API_KEY" not in response.text


def test_only_public_routes_and_models(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/health", "/api/v1/demo"}
    assert all(set(path) == {"get"} for path in schema["paths"].values())
    assert "JobSearchRequest" not in schema["components"]["schemas"]
    assert "multipart/form-data" not in json.dumps(schema)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/job-search", "/api/v1/job-search/", "/upload", "/api/v1/demo", "/health"])
def test_no_post_routes_even_with_live_flag(monkeypatch, path):
    monkeypatch.setenv("ENABLE_LIVE_SEARCH", "true")  # Cannot add a route to this service.
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with TestClient(service.create_app()) as client:
        response = client.post(path, content=b"SYNTHETIC_PRIVATE_SENTINEL")
    assert response.status_code in (404, 405)
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in response.text


def test_rejected_upload_is_never_read(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    messages = []

    async def receive():
        raise AssertionError("Public service must not read an upload body")

    async def send(message):
        messages.append(message)

    asyncio.run(service.create_app()({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/v1/job-search",
        "raw_path": b"/api/v1/job-search", "root_path": "", "query_string": b"",
        "headers": [], "client": ("test", 1), "server": ("test", 80),
    }, receive, send))
    assert messages[0]["status"] == 404


def test_cors_explicit_get_only(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://demo.example")
    with TestClient(service.create_app()) as client:
        allowed = client.get("/api/v1/demo", headers={"Origin": "https://demo.example"})
        assert allowed.headers["access-control-allow-origin"] == "https://demo.example"
        assert "access-control-allow-credentials" not in allowed.headers
        denied = client.get("/health", headers={"Origin": "https://other.example"})
        assert "access-control-allow-origin" not in denied.headers
        for method, status in [("GET", 200), ("POST", 400)]:
            response = client.options("/api/v1/demo", headers={
                "Origin": "https://demo.example", "Access-Control-Request-Method": method,
            })
            assert response.status_code == status
            assert response.headers["access-control-allow-methods"] == "GET"


def test_cors_default_denies_cross_origin(client):
    assert "access-control-allow-origin" not in client.get(
        "/health", headers={"Origin": "https://demo.example"},
    ).headers


@pytest.mark.parametrize("origin", ["*", "https://*.example", "https://user:secret@example.com", "https://example.com/path", "https://example.com?x=1", "https://example.com#frag", "https://example.com:invalid", "https://example.com:0", "https://bad host", "file:///private"])
def test_invalid_cors_fails_closed(monkeypatch, origin):
    monkeypatch.setenv("CORS_ORIGINS", origin)
    with pytest.raises(ValueError, match="explicit HTTP"):
        service.create_app()


@pytest.mark.parametrize("failure", [OSError("SECRET_SENTINEL /private/resume.docx"), ValueError("RAW_RESUME_SENTINEL")])
def test_fixture_errors_sanitized(client, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(Path, "read_text", fail)
    response = client.get("/api/v1/demo")
    assert response.status_code == 503
    assert response.json() == {"error": {
        "code": "demo_unavailable", "message": "The sample demo is temporarily unavailable.",
    }}
    assert client.get("/health").status_code == 200


IMPORT_PROBE = r'''
import builtins
import importlib.util
import os
from pathlib import Path
import sys
import socket
import threading

blocked = ("app.api", "app.api_service", "app.uploads", "app.graph", "app.nodes", "app.tools",
           "app.state", "app.config", "app.live_config", "main", "openai", "langchain", "langchain_openai",
           "langchain_core", "langgraph", "langsmith", "tavily", "requests", "dotenv", "docx")
def forbidden_module(name):
    return any(name == prefix or name.startswith(prefix + ".") for prefix in blocked)
original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    absolute = importlib.util.resolve_name("." * level + name, globals["__package__"]) if level else name
    assert not forbidden_module(absolute), "Forbidden import: " + absolute
    return original_import(name, globals, locals, fromlist, level)
builtins.__import__ = guarded_import

def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        assert not (path.name.startswith(".env") or path.suffix == ".docx" or "data" in path.parts), "Private file read"
sys.addaudithook(audit)
def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden")
original_pair = socket.socketpair
original_connect = socket.socket.connect
local = threading.local()
def socketpair(*args, **kwargs):
    local.pair = True
    try:
        return original_pair(*args, **kwargs)
    finally:
        local.pair = False
def connect(sock, address):
    if getattr(local, "pair", False):
        return original_connect(sock, address)
    forbidden()
socket.socketpair = socketpair
socket.socket.connect = connect
socket.socket.connect_ex = forbidden
socket.getaddrinfo = forbidden

sys.path.insert(0, os.getcwd())
from public_demo.app import app, FIXTURE
assert FIXTURE.is_relative_to(Path.cwd())
from app import api_models as public_models
assert Path(public_models.__file__).is_relative_to(Path.cwd())
import asyncio
import json
async def request(path, method="GET"):
    messages = []
    async def receive():
        raise AssertionError("Public routes must never read request bodies")
    async def send(message):
        messages.append(message)
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
               "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
               "root_path": "", "query_string": b"", "headers": [],
               "client": ("test", 1), "server": ("test", 80)}, receive, send)
    return messages[0]["status"], json.loads(b"".join(m.get("body", b"") for m in messages))
async def check():
    assert await request("/health") == (200, {"status": "ok"})
    status, response = await request("/api/v1/demo")
    assert status == 200
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in json.dumps(response)
    assert (await request("/api/v1/job-search", "POST"))[0] == 404
    assert set((await request("/openapi.json"))[1]["paths"]) == {"/health", "/api/v1/demo"}
asyncio.run(check())
assert not any(forbidden_module(name) for name in sys.modules)
print("PASS: isolated imports and requests, no keys, private files, or network")
'''


@pytest.mark.parametrize("packaged", [False, True])
def test_fresh_process_isolation(tmp_path, packaged):
    root = Path(__file__).resolve().parents[1]
    if packaged:
        archive_path = build_release(tmp_path / "demo.zip")
        with ZipFile(archive_path) as archive:
            assert set(archive.namelist()) == set(RELEASE_FILES)
            assert len(archive.namelist()) == 6
            assert b"\r" not in archive.read("startup.sh")
            archive.extractall(tmp_path / "release")
        root = tmp_path / "release"
    environment = {key: value for key, value in os.environ.items()
                   if key in ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")}
    result = subprocess.run([sys.executable, "-I", "-c", IMPORT_PROBE], cwd=root,
                            env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == "PASS: isolated imports and requests, no keys, private files, or network\n"


def test_release_refuses_overwrite(tmp_path):
    destination = build_release(tmp_path / "release.zip")
    before = destination.read_bytes()
    with pytest.raises(FileExistsError):
        build_release(destination)
    assert destination.read_bytes() == before
