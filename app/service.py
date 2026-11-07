"""The 'analyze' use case, shared by the FastAPI server and the in-browser (Pyodide) build.

Keeping validation and file handling here means both versions of the site behave
exactly the same way and show the same error messages.
"""

from __future__ import annotations

from datetime import date

from .analyzer import analyze
from .parsing import ParseError, extract_text

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_RESUME_CHARS = 60_000
MAX_JOB_CHARS = 30_000


class UserError(ValueError):
    """A problem with the user's input. `status` is the HTTP status the server returns."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def run_analysis(
    job_text: str,
    resume_text: str = "",
    filename: str | None = None,
    data: bytes | None = None,
    *,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    max_resume_chars: int = MAX_RESUME_CHARS,
    max_job_chars: int = MAX_JOB_CHARS,
    today: date | None = None,
) -> dict:
    """Validate the input, extract text from an uploaded file if given, and analyze."""
    source: dict = {"type": "text"}
    if data is not None and filename:
        if len(data) > max_upload_bytes:
            raise UserError(f"Files must be under {max_upload_bytes // (1024 * 1024)} MB.", status=413)
        try:
            parsed = extract_text(filename, data)
        except ParseError as exc:
            raise UserError(str(exc)) from exc
        resume_text = parsed["text"]
        source = {"type": parsed["kind"], "filename": filename, "pages": parsed["pages"]}

    if len(resume_text.strip()) < 50:
        raise UserError("Please upload your resume or paste at least a few lines of it.")
    if len(job_text.strip()) < 50:
        raise UserError("Please paste the job description you're applying for.")
    if len(resume_text) > max_resume_chars:
        raise UserError("Your resume text is too long - is this the right file?")
    if len(job_text) > max_job_chars:
        raise UserError("The job description is too long. Paste just the posting itself.")

    report = analyze(resume_text, job_text, today=today)
    report["source"] = source
    return report
