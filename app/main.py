"""FastAPI application: API routes and the static website.

GET  /              the web app
GET  /api/health    health check
GET  /api/config    feature flags and limits for the UI
GET  /api/sample    a sample resume + job post
POST /api/analyze   resume (file or text) + job description -> match report
POST /api/coach     optional Claude-powered rewrite suggestions
GET  /api/docs      interactive API docs
"""

from __future__ import annotations

import logging
import math

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .analyzer import analyze
from .coach import Coach, CoachError
from .config import STATIC_DIR, Settings
from .parsing import SUPPORTED_EXTENSIONS, ParseError, extract_text
from .samples import SAMPLE_JOB, SAMPLE_RESUME
from .security import BodySizeLimitMiddleware, RateLimiter, SecurityHeadersMiddleware, client_ip

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("resumeradar")


class CoachRequest(BaseModel):
    resume_text: str = Field(min_length=50)
    job_text: str = Field(min_length=50)
    missing_skills: list[str] = Field(default_factory=list, max_length=40)
    weak_bullets: list[str] = Field(default_factory=list, max_length=20)


def create_app(settings: Settings | None = None, coach: Coach | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if coach is None and settings.coach_enabled:
        coach = Coach(settings.anthropic_api_key, settings.coach_model)
    analyze_limiter = RateLimiter(settings.analyze_per_minute)
    coach_limiter = RateLimiter(settings.coach_per_minute)

    app = FastAPI(
        title="ResumeRadar API",
        version=__version__,
        description="Match a resume against a job description and get actionable feedback.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes + 512 * 1024)
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("ResumeRadar v%s starting (AI coach %s)", __version__, "ON" if coach else "OFF")

    def limit(limiter: RateLimiter, request: Request) -> None:
        allowed, retry_after = limiter.hit(client_ip(request, settings.trust_proxy))
        if not allowed:
            wait = max(1, math.ceil(retry_after))
            raise HTTPException(429, f"Too many requests - please wait {wait}s.", headers={"Retry-After": str(wait)})

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/config", tags=["meta"])
    async def config() -> dict:
        return {
            "version": __version__,
            "coach_enabled": coach is not None,
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            "max_resume_chars": settings.max_resume_chars,
            "max_job_chars": settings.max_job_chars,
            "file_types": list(SUPPORTED_EXTENSIONS),
        }

    @app.get("/api/sample", tags=["meta"])
    async def sample() -> dict:
        return {"resume": SAMPLE_RESUME, "job": SAMPLE_JOB}

    @app.post("/api/analyze", tags=["analysis"])
    async def analyze_route(
        request: Request,
        job_text: str = Form(""),
        resume_text: str = Form(""),
        resume_file: UploadFile | None = File(None),
    ) -> dict:
        limit(analyze_limiter, request)

        source = {"type": "text"}
        if resume_file is not None and resume_file.filename:
            data = await resume_file.read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise HTTPException(413, f"Files must be under {settings.max_upload_bytes // (1024 * 1024)} MB.")
            try:
                parsed = await run_in_threadpool(extract_text, resume_file.filename, data)
            except ParseError as exc:
                raise HTTPException(400, str(exc)) from exc
            resume_text = parsed["text"]
            source = {"type": parsed["kind"], "filename": resume_file.filename, "pages": parsed["pages"]}

        if len(resume_text.strip()) < 50:
            raise HTTPException(400, "Please upload your resume or paste at least a few lines of it.")
        if len(job_text.strip()) < 50:
            raise HTTPException(400, "Please paste the job description you're applying for.")
        if len(resume_text) > settings.max_resume_chars:
            raise HTTPException(400, "Your resume text is too long - is this the right file?")
        if len(job_text) > settings.max_job_chars:
            raise HTTPException(400, "The job description is too long. Paste just the posting itself.")

        report = await run_in_threadpool(analyze, resume_text, job_text)
        report["source"] = source
        return report

    @app.post("/api/coach", tags=["analysis"])
    async def coach_route(body: CoachRequest, request: Request) -> dict:
        if coach is None:
            raise HTTPException(503, "The AI coach isn't enabled on this server (no ANTHROPIC_API_KEY).")
        if len(body.resume_text) > settings.max_resume_chars or len(body.job_text) > settings.max_job_chars:
            raise HTTPException(400, "The resume or job description is too long.")
        limit(coach_limiter, request)
        try:
            result = await coach.review(body.resume_text, body.job_text, body.missing_skills, body.weak_bullets)
        except CoachError as exc:
            raise HTTPException(502, str(exc)) from exc
        return result.model_dump()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    return app


app = create_app()
