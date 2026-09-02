"""Read-only ASGI entrypoint. Never import app.api or the live workflow here."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api_models import ErrorResponse, HealthResponse, JobSearchResponse


FIXTURE = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "demo.json"


def configured_origins() -> list[str]:
    """Only explicit origins; no credentials, regexes, paths, or wildcards."""
    origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "").split(",") if value.strip()]
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            invalid = (
                parsed.scheme not in ("https", "http") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or "*" in origin
                or any(character.isspace() for character in origin)
                or "\\" in origin or parsed.port == 0
            )
        except ValueError:
            invalid = True
        if invalid:
            raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins without paths.")
    return origins


def safe_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app() -> FastAPI:
    application = FastAPI(
        title="AI Job Search — Synthetic Demo", version="1.0.0", debug=False,
        docs_url=None, redoc_url=None, redirect_slashes=False,
    )
    application.add_middleware(
        CORSMiddleware, allow_origins=configured_origins(), allow_credentials=False,
        allow_methods=["GET"], allow_headers=[],
    )

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        return safe_error(exc.status_code, "invalid_request", "The request could not be processed.")

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        return safe_error(500, "internal_error", "The demo could not be loaded.")

    @application.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse()

    @application.get(
        "/api/v1/demo", response_model=JobSearchResponse,
        responses={503: {"model": ErrorResponse}},
    )
    def demo():
        try:
            # A fixed packaged resource, never a caller-selected file or environment path.
            return JobSearchResponse.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
        except Exception:
            # Keep parsing errors, local paths and file contents out of responses and logs.
            return safe_error(503, "demo_unavailable", "The sample demo is temporarily unavailable.")

    return application


app = create_app()
