"""Tests for the shared service layer and the GitHub Pages (browser / Pyodide) build."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.browser import analyze_json
from app.config import Settings
from app.main import create_app
from app.samples import SAMPLE_JOB, SAMPLE_RESUME
from app.service import UserError, run_analysis
from scripts.build_pages import BROWSER_MODULES, build
from tests.helpers import make_pdf


def test_run_analysis_text_and_file():
    report = run_analysis(SAMPLE_JOB, SAMPLE_RESUME)
    assert report["source"] == {"type": "text"} and 0 <= report["score"] <= 100

    pdf = make_pdf(["Sam Lee sam@example.com", "SKILLS", "Python, SQL, Airflow, Spark, AWS, Docker and Kubernetes"])
    report = run_analysis(SAMPLE_JOB, filename="cv.pdf", data=pdf)
    assert report["source"]["type"] == "pdf"
    assert "Kubernetes" in {s["name"] for s in report["skills"]["matched"]}


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"job_text": SAMPLE_JOB, "resume_text": "too short"}, 400),
        ({"job_text": "too short", "resume_text": SAMPLE_RESUME}, 400),
        ({"job_text": SAMPLE_JOB, "filename": "cv.exe", "data": b"x" * 100}, 400),
        ({"job_text": SAMPLE_JOB, "filename": "cv.txt", "data": b"x" * 2000, "max_upload_bytes": 1000}, 413),
    ],
)
def test_run_analysis_errors(kwargs, status):
    with pytest.raises(UserError) as info:
        run_analysis(**kwargs)
    assert info.value.status == status


def test_browser_entry_point(tmp_path):
    upload = tmp_path / "upload.bin"
    upload.write_bytes(SAMPLE_RESUME.encode())
    result = json.loads(analyze_json(SAMPLE_JOB, "", "resume.txt", str(upload)))
    assert result["ok"] is True and result["report"]["source"]["filename"] == "resume.txt"
    assert not upload.exists()  # the uploaded copy is deleted right away

    error = json.loads(analyze_json(SAMPLE_JOB, "short"))
    assert error == {"ok": False, "error": "Please upload your resume or paste at least a few lines of it."}


def test_build_pages_output(tmp_path):
    site = build(tmp_path / "_site")
    for path in ("index.html", "static/js/engine.js", "static/css/styles.css", "sample.json", ".nojekyll"):
        assert (site / path).is_file(), path
    config = json.loads((site / "browser-mode.json").read_text())
    assert config["mode"] == "browser" and config["modules"] == BROWSER_MODULES
    assert all((site / "py" / "app" / name).is_file() for name in BROWSER_MODULES)
    # Relative asset paths so the site works under /resume-radar/ on GitHub Pages.
    assert 'href="/static' not in (site / "index.html").read_text()


def test_browser_modules_only_use_stdlib_and_pypdf():
    """Everything shipped to the browser must run in Pyodide: no FastAPI, no Anthropic SDK."""
    for name in BROWSER_MODULES:
        source = open(f"app/{name}", encoding="utf-8").read()
        imports = re.findall(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE)
        third_party = {i.split(".")[0] for i in imports if not i.startswith(".")} - {
            "__future__", "base64", "binascii", "collections", "dataclasses", "datetime", "io", "json", "os",
            "re", "typing", "unicodedata", "xml", "zipfile", "pypdf",
        }
        assert not third_party, f"{name} imports {third_party}"


def test_server_has_no_browser_mode_file():
    client = TestClient(create_app(Settings()))
    assert client.get("/browser-mode.json").status_code == 404  # so the UI uses the server engine
