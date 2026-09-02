"""HTTP adapter only; matching and verification remain in the existing graph."""

import os
from pathlib import Path
from typing import Annotated, Callable
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.api_models import ErrorResponse, HealthResponse, JobSearchRequest, JobSearchResponse
from app.api_service import (
    ProviderConfigurationError, ProviderServiceError, build_response, run_workflow,
)
from app.uploads import (
    DOCX_MEDIA_TYPE, MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES,
    UnreadableResume, extract_uploaded_resume,
)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class BodyLimitMiddleware:
    """Bound multipart bodies, even without Content-Length, before disk spooling."""

    def __init__(self, app, *, live_enabled: bool):
        self.app = app
        self.live_enabled = live_enabled

    async def __call__(self, scope, receive, send):
        # Bound every POST so mounted/root-path and trailing-slash variants
        # cannot bypass the cap before routing or multipart parsing.
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        if not self.live_enabled:
            response = error_response(403, "live_search_disabled", "Live analysis is disabled. Try the sample demo.")
            return await response(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                response = error_response(413, "upload_too_large", "Upload exceeds the request size limit.")
                return await response(scope, receive, send)
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent = False

        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def get_workflow_runner() -> Callable[[str, str], dict]:
    return run_workflow


def configured_origins() -> list[str]:
    origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment or "*" in origin):
            raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins without paths.")
    return origins


def create_app() -> FastAPI:
    application = FastAPI(title="AI Job Search Agent", version="0.2.0", debug=False)
    application.add_middleware(
        BodyLimitMiddleware,
        live_enabled=os.getenv("ENABLE_LIVE_SEARCH", "false").lower() == "true",
    )
    application.add_middleware(
        CORSMiddleware, allow_origins=configured_origins(), allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error_response(422, "invalid_request", "Provide a DOCX resume and a non-empty search_request (at most 2000 characters).")

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(exc.status_code, "invalid_request", "The request could not be processed.")

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        return error_response(500, "internal_error", "The job search could not be completed.")

    @application.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse()

    @application.get("/api/v1/demo", response_model=JobSearchResponse)
    def demo():
        """Illustrative, synthetic data only; never constructs or invokes providers."""
        fixture = Path(__file__).with_name("fixtures") / "demo.json"
        return JobSearchResponse.model_validate_json(fixture.read_text(encoding="utf-8"))

    @application.post(
        "/api/v1/job-search", response_model=JobSearchResponse,
        responses={status: {"model": ErrorResponse} for status in (400, 403, 413, 415, 422, 502, 503, 500)},
    )
    async def job_search(
        request: Request,
        resume: Annotated[UploadFile, File(description="DOCX resume, maximum 5 MiB")],
        search_request: Annotated[str, Form(min_length=1, max_length=2000)],
        runner: Annotated[Callable, Depends(get_workflow_runner)],
    ):
        try:
            form = await request.form()
            if (set(form.keys()) != {"resume", "search_request"}
                    or len(form.getlist("resume")) != 1
                    or len(form.getlist("search_request")) != 1):
                return error_response(422, "invalid_request", "Only one resume and one search_request are supported.")
            try:
                payload = JobSearchRequest(search_request=search_request)
            except ValidationError:
                return error_response(422, "invalid_request", "search_request must contain 1 to 2000 non-whitespace characters.")
            if (not (resume.filename or "").lower().endswith(".docx")
                    or resume.content_type not in (DOCX_MEDIA_TYPE, "application/octet-stream")):
                return error_response(415, "unsupported_file_type", "Upload a DOCX resume.")
            content = await resume.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                return error_response(413, "upload_too_large", "Resume must not exceed 5 MiB.")
        finally:
            # Includes rolled-to-disk multipart uploads; no permanent copy exists.
            await resume.close()

        try:
            resume_text = await run_in_threadpool(extract_uploaded_resume, content)
            state = await run_in_threadpool(runner, payload.search_request, resume_text)
            return build_response(state)
        except UnreadableResume:
            return error_response(422, "unreadable_docx", "The DOCX could not be read or contains no body paragraph or table text.")
        except ProviderConfigurationError:
            return error_response(503, "provider_not_configured", "Required provider configuration is missing or invalid.")
        except ProviderServiceError:
            return error_response(502, "provider_failure", "A required provider could not complete the search.")
        except Exception:
            # Return inside CORS middleware so allowed browsers can read the
            # safe error envelope, without exposing provider/parser details.
            return error_response(500, "internal_error", "The job search could not be completed.")

    return application


app = create_app()
