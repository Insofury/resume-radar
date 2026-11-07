"""Unit tests for the analysis engine (skills, text, experience, job parsing, checks)."""

from __future__ import annotations

from datetime import date

from app.analyzer import analyze
from app.checks import bullet_feedback, has_metric, starts_with_action_verb, weak_start
from app.experience import claimed_years, date_ranges, highest_degree, lowest_degree, total_years, years_mentioned
from app.job import analyze_job, classify_lines
from app.resume import contact_info, extract_bullets, parse_structure
from app.samples import SAMPLE_JOB, SAMPLE_RESUME
from app.skills import find_skills
from app.textutils import extract_keywords, normalize_text, stem

TODAY = date(2026, 11, 8)


# ------------------------------------------------------------------ skills
def test_finds_skills_with_symbols_and_aliases():
    found = find_skills("Built services in C++, C# and .NET with Node.js, k8s and Postgres; CI/CD on GitHub Actions.")
    for name in ("C++", "C#", ".NET", "Node.js", "Kubernetes", "PostgreSQL", "CI/CD", "GitHub Actions"):
        assert name in found, name


def test_longer_skill_wins_over_contained_one():
    found = find_skills("Shipped a React Native app and a Spring Boot API.")
    assert "React Native" in found and "Spring Boot" in found
    assert "React" not in found and "Spring" not in found


def test_case_sensitive_and_ambiguous_words():
    assert "Go" in find_skills("Services written in Go and Python.")
    assert "Go" not in find_skills("Go above and beyond for customers.")
    assert "React" not in find_skills("Able to react quickly to incidents.")
    assert "R" in find_skills("Analysis in Python, R and SQL.")
    assert "R" not in find_skills("Led R&D for the new product.")
    assert "Java" not in find_skills("Expert in JavaScript.")


# ------------------------------------------------------------------- text
def test_stem_groups_word_forms():
    assert stem("manage") == stem("managed") == stem("managing")
    assert stem("developing") == stem("develop")


def test_normalize_merges_lone_bullet_glyphs():
    assert normalize_text("•\nBuilt an API\n\n\n\nDone") == "• Built an API\n\nDone"


def test_keywords_skip_company_names_and_generic_words():
    text = "Acme Corp builds logistics software. Our logistics platform handles real-time routing at scale. Real-time routing matters."
    terms = [k["term"] for k in extract_keywords(text)]
    assert "logistics" in terms and "real-time routing" in terms
    assert not {"acme", "corp", "our"} & set(terms)


# ------------------------------------------------------------- experience
def test_date_ranges_and_overlap_merge():
    text = "Jan 2020 - Dec 2021\n06/2021 - Present\n2015 - 2016"
    ranges = date_ranges(text, TODAY)
    assert len(ranges) == 3
    # 2020-01 .. 2026-11 merged (82 months) + 2015-06 .. 2016-06 (12 months)
    assert total_years(ranges) == round((82 + 12) / 12, 1)


def test_degrees_and_years():
    assert highest_degree("B.S. in Physics, MBA from XYZ") == "master"
    assert lowest_degree("Bachelor's degree required; Master's preferred") == "bachelor"
    assert highest_degree("Scrum Master certified") is None
    assert years_mentioned("5+ years of experience with Python, 2 years with AWS") == [5, 2]
    assert claimed_years("Engineer with 7+ years of professional experience") == 7


# -------------------------------------------------------------------- job
def test_job_required_vs_preferred():
    job = analyze_job(
        "Requirements\n- Python and Docker\n- 3+ years of experience\n\nNice to have\n- Kubernetes skills\n- Terraform\n"
    )
    importance = {s.name: s.importance for s in job.skills}
    assert importance["Python"] == importance["Docker"] == "required"
    assert importance["Kubernetes"] == importance["Terraform"] == "preferred"
    assert job.years_required == 3


def test_inline_preferred_cue():
    job = analyze_job("You have:\n- SQL\n- Experience with Airflow is a plus\n")
    importance = {s.name: s.importance for s in job.skills}
    assert importance == {"SQL": "required", "Airflow": "preferred"}


def test_short_skill_line_is_not_a_heading():
    kinds = [k for _, _, k in classify_lines("Nice to have:\n- Kubernetes skills\n- Go")]
    assert kinds == ["preferred", "preferred", "preferred"]


# ----------------------------------------------------------------- resume
def test_structure_contact_and_bullets():
    text = normalize_text(SAMPLE_RESUME)
    structure = parse_structure(text)
    assert {"summary", "experience", "education", "skills", "projects"} <= set(structure.sections)
    contact = contact_info(text)
    assert contact["email"] == "alex.morgan@example.com"
    assert contact["linkedin"] and contact["github"] and contact["phone"]
    bullets = extract_bullets(structure)
    assert len(bullets) == 10
    assert bullets[0].startswith("Built a FastAPI service")


# ----------------------------------------------------------------- checks
def test_bullet_helpers():
    assert starts_with_action_verb("Reduced costs by 30%")
    assert weak_start("Responsible for the database") == "responsible for"
    assert has_metric("Cut load time by 40%") and has_metric("Served 2M+ users")
    assert not has_metric("Joined in 2021 as an engineer")
    feedback = bullet_feedback(["Worked on the API", "Reduced latency by 40% for 1M users"])
    assert len(feedback) == 1 and "No measurable result" in feedback[0]["issues"]


# --------------------------------------------------------------- analyzer
def test_sample_analysis_end_to_end():
    report = analyze(SAMPLE_RESUME, SAMPLE_JOB, today=TODAY)
    assert 40 <= report["score"] <= 75
    matched = {s["name"] for s in report["skills"]["matched"]}
    missing = {s["name"]: s["importance"] for s in report["skills"]["missing"]}
    partial = {s["name"]: s["via"] for s in report["skills"]["partial"]}
    assert {"Python", "FastAPI", "Docker", "AWS", "PostgreSQL"} <= matched
    assert missing["Kubernetes"] == "required" and missing["Terraform"] == "preferred"
    assert partial["Caching"] == "Redis"
    assert report["requirements"]["years_required"] == 5 and report["requirements"]["years_met"] is True
    assert report["requirements"]["degree_met"] is True
    assert any("Kubernetes" in r for r in report["recommendations"])
    statuses = {c["id"]: c["status"] for c in report["checks"]}
    assert statuses["email"] == "pass" and statuses["weak_phrases"] == "fail"
    assert sum(p["weight"] for p in report["breakdown"]) == 100


def test_strong_resume_scores_higher_than_weak_one():
    strong = analyze(SAMPLE_RESUME + "\nKubernetes, Kafka, Terraform, Prometheus, Grafana, microservices, "
                     "distributed systems, system design, observability", SAMPLE_JOB, today=TODAY)
    weak = analyze("Jane Doe\njane@example.com\nI like computers and I am a hard-working team player. " * 3,
                   SAMPLE_JOB, today=TODAY)
    base = analyze(SAMPLE_RESUME, SAMPLE_JOB, today=TODAY)
    assert strong["score"] > base["score"] > weak["score"]
