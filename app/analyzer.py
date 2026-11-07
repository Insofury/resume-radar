"""The analysis pipeline: resume text + job description -> match report.

Score = weighted average of four parts (parts that don't apply are skipped and
the weights re-normalised):

    Skills match            45%   weighted coverage of the job's skills
    Keyword match           20%   coverage of the job's most repeated terms
    Experience & education  15%   years of experience and degree level
    Resume quality          20%   ATS-friendliness and writing checks
"""

from __future__ import annotations

from datetime import date

from .checks import bullet_feedback, has_metric, quality_score, run_checks, starts_with_action_verb
from .experience import (
    DEGREE_LABELS,
    DEGREE_LEVELS,
    claimed_years,
    date_ranges,
    highest_degree,
    total_years,
)
from .job import analyze_job
from .resume import contact_info, extract_bullets, parse_structure
from .skills import ALL_ALIASES, RELATED, SKILLS_BY_NAME, find_skills
from .textutils import contains_stems, extract_keywords, normalize_text, stem_sequence, word_count

WEIGHTS = {"skills": 45, "keywords": 20, "requirements": 15, "quality": 20}


def _label(score: int) -> str:
    if score >= 80:
        return "Excellent match"
    if score >= 65:
        return "Good match"
    if score >= 50:
        return "Fair match"
    return "Needs work"


def _fmt_list(items: list[str], limit: int = 6) -> str:
    items = items[:limit]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def analyze(resume_text: str, job_text: str, today: date | None = None) -> dict:
    today = today or date.today()
    resume_text = normalize_text(resume_text)
    job_text = normalize_text(job_text)

    # ---------------------------------------------------------------- job
    job = analyze_job(job_text)

    # ------------------------------------------------------------- resume
    structure = parse_structure(resume_text)
    resume_skills = find_skills(resume_text)
    bullets = extract_bullets(structure)
    contact = contact_info(resume_text)

    # experience: dates from the experience section if we found one, else everywhere but education
    exp_text = structure.text_of("experience") if structure.has("experience") else resume_text
    if not structure.has("experience") and structure.has("education"):
        edu = structure.text_of("education")
        exp_text = exp_text.replace(edu, "")
    ranges = date_ranges(exp_text, today)
    years_from_dates = total_years(ranges) if ranges else None
    claimed = claimed_years(resume_text)
    years_found = max(v for v in (years_from_dates, claimed) if v is not None) if (ranges or claimed) else None
    degree_found = highest_degree(resume_text)

    # ------------------------------------------------------------- skills
    matched, partial, missing = [], [], []
    for skill in job.skills:
        item = {"name": skill.name, "category": skill.category, "importance": skill.importance, "soft": skill.soft}
        if skill.name in resume_skills:
            matched.append((skill, item))
            continue
        via = next((r for r in RELATED.get(skill.name, ()) if r in resume_skills), None)
        if via:
            item["via"] = via
            partial.append((skill, item))
        else:
            missing.append((skill, item))
    total_weight = sum(s.weight for s in job.skills)
    earned = sum(s.weight for s, _ in matched) + 0.5 * sum(s.weight for s, _ in partial)
    skills_score = round(100 * earned / total_weight) if total_weight else None
    job_skill_names = {s.name for s in job.skills}
    extra = sorted(
        (
            {"name": n, "category": SKILLS_BY_NAME[n].category}
            for n in resume_skills
            if n not in job_skill_names and not SKILLS_BY_NAME[n].soft
        ),
        key=lambda d: (d["category"], d["name"]),
    )

    # ----------------------------------------------------------- keywords
    keywords = extract_keywords(job.keyword_text, exclude=set(ALL_ALIASES), top_n=15)
    resume_stems = stem_sequence(resume_text)
    kw_matched = [k["term"] for k in keywords if contains_stems(resume_stems, k["stems"])]
    kw_missing = [k["term"] for k in keywords if not contains_stems(resume_stems, k["stems"])]
    keyword_score = round(100 * len(kw_matched) / len(keywords)) if keywords else None

    # ------------------------------------------------------- requirements
    req_parts = []
    years_met = degree_met = None
    if job.years_required:
        ratio = min((years_found or 0) / job.years_required, 1.0)
        years_met = ratio >= 1.0
        req_parts.append(ratio * 100)
    if job.degree_required:
        if degree_found:
            degree_met = DEGREE_LEVELS[degree_found] >= DEGREE_LEVELS[job.degree_required]
            req_parts.append(100 if degree_met else 60)
        else:
            degree_met = False
            req_parts.append(30)
    requirements_score = round(sum(req_parts) / len(req_parts)) if req_parts else None

    # ------------------------------------------------------------ quality
    summary_text = structure.text_of("summary")
    checks = run_checks(
        word_total=word_count(resume_text),
        contact=contact,
        sections=set(structure.sections),
        bullets=bullets,
        pronoun_text="\n".join(bullets) + "\n" + summary_text,
        full_text=resume_text,
        has_dates=bool(ranges),
    )
    quality = quality_score(checks)

    # -------------------------------------------------------------- score
    parts = {
        "skills": skills_score,
        "keywords": keyword_score,
        "requirements": requirements_score,
        "quality": quality,
    }
    active = {k: v for k, v in parts.items() if v is not None}
    weight_sum = sum(WEIGHTS[k] for k in active)
    score = round(sum(WEIGHTS[k] * v for k, v in active.items()) / weight_sum) if weight_sum else 0

    tech_total = [s for s in job.skills if not s.soft]
    tech_hit = [s for s, _ in matched if not s.soft]
    tech_partial = [s for s, _ in partial if not s.soft]
    required_total = [s for s in tech_total if s.importance == "required"]
    required_hit = [s for s in tech_hit if s.importance == "required"]
    breakdown = [
        {
            "id": "skills", "label": "Skills match", "score": skills_score, "weight": WEIGHTS["skills"],
            "detail": (
                f"{len(matched)} matched, {len(partial)} related, {len(missing)} missing" if job.skills
                else "No recognisable skills in the job post"
            ),
        },
        {
            "id": "keywords", "label": "Keyword match", "score": keyword_score, "weight": WEIGHTS["keywords"],
            "detail": f"{len(kw_matched)} of {len(keywords)} key terms" if keywords else "Not enough text to compare",
        },
        {
            "id": "requirements", "label": "Experience & education", "score": requirements_score,
            "weight": WEIGHTS["requirements"],
            "detail": "No explicit years or degree requirement" if requirements_score is None
            else "Years of experience and degree level",
        },
        {
            "id": "quality", "label": "Resume quality", "score": quality, "weight": WEIGHTS["quality"],
            "detail": f"{sum(c.status == 'pass' for c in checks)} of {len(checks)} checks passed",
        },
    ]

    # ---------------------------------------------------- recommendations
    recs: list[str] = []
    missing_required = [i["name"] for s, i in missing if s.importance == "required" and not s.soft]
    missing_preferred = [i["name"] for s, i in missing if s.importance == "preferred" and not s.soft]
    missing_soft = [i["name"] for s, i in missing if s.soft]
    if missing_required:
        recs.append(
            f"Add the must-have skills you genuinely have: {_fmt_list(missing_required)}. "
            "List them under Skills and prove them in a bullet that shows what you built or achieved with them."
        )
    related_required = [f"{i['name']} (you show {i['via']})" for s, i in partial if not s.soft]
    if related_required:
        recs.append(
            f"You have related experience - name the exact skill the post uses: {_fmt_list(related_required, 4)}."
        )
    if years_met is False:
        found = f"about {years_found:g}" if years_found else "no clear dates for"
        recs.append(
            f"The job asks for {job.years_required}+ years of experience and your resume shows {found} years. "
            "Make sure every role, internship and freelance project has dates, and lead with your most relevant wins."
        )
    if degree_met is False:
        recs.append(
            f"The job mentions a {DEGREE_LABELS[job.degree_required]} degree. If you have it (or an equivalent "
            "certification), state it clearly in an Education section."
        )
    if kw_missing:
        recs.append(
            f"Mirror the job's language where it truthfully applies - e.g. {_fmt_list([f'“{k}”' for k in kw_missing], 5)}."
        )
    if missing_preferred:
        recs.append(f"Nice-to-haves worth mentioning if you have them: {_fmt_list(missing_preferred)}.")
    if missing_soft:
        recs.append(
            f"Show soft skills through results rather than adjectives - the post values {_fmt_list([s.lower() for s in missing_soft], 4)}."
        )
    for check in sorted(checks, key=lambda c: (c.status != "fail", -c.weight)):
        if check.status != "pass" and len(recs) < 9:
            recs.append(check.tip)

    if tech_total:
        summary = (
            f"Your resume shows {len(tech_hit)} of the {len(tech_total)} technical skills this job mentions"
            + (f" (plus related experience for {len(tech_partial)} more)" if tech_partial else "")
            + (f", including {len(required_hit)} of {len(required_total)} must-haves." if required_total else ".")
        )
    elif job.skills:
        summary = f"Your resume shows {len(matched)} of the {len(job.skills)} skills this job mentions."
    else:
        summary = "We couldn't find well-known skills in this job post, so the score leans on keywords and resume quality."

    return {
        "score": score,
        "label": _label(score),
        "summary": summary,
        "breakdown": breakdown,
        "skills": {
            "matched": [i for _, i in matched],
            "partial": [i for _, i in partial],
            "missing": [i for _, i in missing],
            "extra": extra,
        },
        "keywords": {"matched": kw_matched, "missing": kw_missing},
        "requirements": {
            "years_required": job.years_required,
            "years_found": years_found,
            "years_met": years_met,
            "degree_required": DEGREE_LABELS.get(job.degree_required) if job.degree_required else None,
            "degree_found": DEGREE_LABELS.get(degree_found) if degree_found else None,
            "degree_met": degree_met,
        },
        "checks": [c.to_dict() for c in checks],
        "bullets": bullet_feedback(bullets),
        "recommendations": recs,
        "contact": contact,
        "stats": {
            "resume_words": word_count(resume_text),
            "job_words": word_count(job_text),
            "bullets": len(bullets),
            "quantified_bullets": sum(has_metric(b) for b in bullets),
            "action_verb_bullets": sum(starts_with_action_verb(b) for b in bullets),
            "sections": sorted(structure.sections),
        },
        "resume_text": resume_text,
    }
