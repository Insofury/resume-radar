"""HTTP-level tests for every endpoint, plus file parsing and the AI coach."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.coach import FALLBACK_BETA, Coach, CoachError
from app.config import Settings
from app.main import create_app
from app.parsing import ParseError, extract_text
from app.samples import SAMPLE_JOB, SAMPLE_RESUME
from tests.helpers import make_docx, make_pdf

RESUME_LINES = [
    "Sam Lee - sam@example.com - linkedin.com/in/samlee",
    "EXPERIENCE",
    "Data Engineer, Acme  Mar 2021 - Present",
    "- Built Airflow pipelines in Python processing 5TB daily",
    "EDUCATION",
    "B.Sc. Computer Science 2017 - 2020",
    "SKILLS",
    "Python, SQL, Airflow, Spark, AWS",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings()))


# ---------------------------------------------------------------- parsing
def test_extract_pdf_docx_and_text():
    pdf = extract_text("cv.pdf", make_pdf(RESUME_LINES))
    assert pdf["kind"] == "pdf" and pdf["pages"] == 1 and "Airflow pipelines" in pdf["text"]

    docx = extract_text("cv.docx", make_docx([(line, line.startswith("-")) for line in RESUME_LINES]))
    assert docx["kind"] == "docx" and "• - Built Airflow" in docx["text"]

    txt = extract_text("cv.txt", "\n".join(RESUME_LINES).encode())
    assert txt["kind"] == "text" and "Spark" in txt["text"]


def test_extract_rejects_bad_files():
    with pytest.raises(ParseError):
        extract_text("cv.exe", b"MZ" * 100)
    with pytest.raises(ParseError):
        extract_text("cv.pdf", b"%PDF-1.4 not really a pdf")
    with pytest.raises(ParseError):
        extract_text("cv.pdf", make_pdf(["Hi"]))  # almost no text -> probably a scan
    with pytest.raises(ParseError):
        extract_text("cv.docx", b"not a zip")


# ---------------------------------------------------------------- routes
def test_meta_routes(client):
    assert client.get("/api/health").json()["status"] == "ok"
    config = client.get("/api/config").json()
    assert config["coach_enabled"] is False and config["max_upload_mb"] == 5
    sample = client.get("/api/sample").json()
    assert "Alex Morgan" in sample["resume"] and "Northwind" in sample["job"]
    page = client.get("/")
    assert page.status_code == 200 and "ResumeRadar" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.head("/").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200


def test_analyze_with_text(client):
    res = client.post("/api/analyze", data={"resume_text": SAMPLE_RESUME, "job_text": SAMPLE_JOB})
    assert res.status_code == 200
    report = res.json()
    assert 0 <= report["score"] <= 100 and report["source"] == {"type": "text"}
    assert {"breakdown", "skills", "keywords", "requirements", "checks", "bullets", "recommendations"} <= set(report)


def test_analyze_with_pdf_upload(client):
    files = {"resume_file": ("resume.pdf", make_pdf(RESUME_LINES), "application/pdf")}
    res = client.post("/api/analyze", data={"job_text": SAMPLE_JOB}, files=files)
    assert res.status_code == 200, res.text
    report = res.json()
    assert report["source"]["type"] == "pdf" and report["source"]["filename"] == "resume.pdf"
    assert "Python" in {s["name"] for s in report["skills"]["matched"]}


def test_analyze_validation_errors(client):
    assert client.post("/api/analyze", data={"resume_text": SAMPLE_RESUME, "job_text": "short"}).status_code == 400
    assert client.post("/api/analyze", data={"resume_text": "tiny", "job_text": SAMPLE_JOB}).status_code == 400
    bad = {"resume_file": ("resume.exe", b"x" * 200, "application/octet-stream")}
    res = client.post("/api/analyze", data={"job_text": SAMPLE_JOB}, files=bad)
    assert res.status_code == 400 and "Unsupported" in res.json()["detail"]


def test_upload_size_limit():
    client = TestClient(create_app(Settings(max_upload_bytes=1000)))
    big = {"resume_file": ("resume.txt", b"a" * 5000, "text/plain")}
    assert client.post("/api/analyze", data={"job_text": SAMPLE_JOB}, files=big).status_code == 413


def test_rate_limit():
    client = TestClient(create_app(Settings(analyze_per_minute=2)))
    body = {"resume_text": SAMPLE_RESUME, "job_text": SAMPLE_JOB}
    assert client.post("/api/analyze", data=body).status_code == 200
    assert client.post("/api/analyze", data=body).status_code == 200
    res = client.post("/api/analyze", data=body)
    assert res.status_code == 429 and int(res.headers["retry-after"]) >= 1


def test_coach_disabled_returns_503(client):
    body = {"resume_text": SAMPLE_RESUME, "job_text": SAMPLE_JOB}
    assert client.post("/api/coach", json=body).status_code == 503


# ------------------------------------------------------------------ coach
COACH_JSON = {
    "tailored_summary": "Backend engineer focused on Python APIs.",
    "bullet_rewrites": [{"original": "Worked on CI", "improved": "Automated CI with GitHub Actions", "why": "Verb + tool"}],
    "top_tips": ["Mention Kubernetes if you have used it."],
}


def fake_client(content, stop_reason="end_turn", captured=None):
    async def create(**params):
        if captured is not None:
            captured.update(params)
        return SimpleNamespace(content=content, stop_reason=stop_reason)

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def test_coach_request_params_use_structured_output_and_fallbacks():
    params = Coach("sk-test", client=object()).request_params("hi")
    assert params["model"] == "claude-opus-5-5"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert params["output_config"]["effort"] == "medium"
    assert params["fallbacks"] == "default" and params["betas"] == [FALLBACK_BETA]
    assert "fallbacks" not in Coach("sk-test", model="claude-haiku-5-5", client=object()).request_params("hi")


def test_coach_parses_answer_after_fallback_block():
    content = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="fallback"),
        text_block(json.dumps(COACH_JSON)),
    ]
    captured = {}
    coach = Coach("sk-test", client=fake_client(content, captured=captured))
    result = asyncio.run(coach.review(SAMPLE_RESUME, SAMPLE_JOB, ["Kubernetes"], ["Worked on CI"]))
    assert result.bullet_rewrites[0].improved == "Automated CI with GitHub Actions"
    prompt = captured["messages"][0]["content"]
    assert "<job_description>" in prompt and "Kubernetes" in prompt and "Worked on CI" in prompt


@pytest.mark.parametrize(
    ("content", "stop_reason"),
    [([text_block("not json")], "end_turn"), ([], "refusal"), ([text_block('{"tailored')], "max_tokens")],
)
def test_coach_errors_are_friendly(content, stop_reason):
    coach = Coach("sk-test", client=fake_client(content, stop_reason))
    with pytest.raises(CoachError):
        asyncio.run(coach.review(SAMPLE_RESUME, SAMPLE_JOB, [], []))


def test_coach_api_error_is_mapped():
    async def create(**params):
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)

    coach = Coach("sk-test", client=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))))
    with pytest.raises(CoachError, match="busy"):
        asyncio.run(coach.review(SAMPLE_RESUME, SAMPLE_JOB, [], []))


def test_coach_route_with_fake_coach():
    coach = Coach("sk-test", client=fake_client([text_block(json.dumps(COACH_JSON))]))
    client = TestClient(create_app(Settings(), coach=coach))
    assert client.get("/api/config").json()["coach_enabled"] is True
    res = client.post("/api/coach", json={"resume_text": SAMPLE_RESUME, "job_text": SAMPLE_JOB})
    assert res.status_code == 200 and res.json()["top_tips"] == COACH_JSON["top_tips"]
