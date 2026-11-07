"""Resume quality (ATS-friendliness and writing) checks.

Each check returns a status - "pass", "warn" or "fail" - with a short detail and a
tip. The weighted average becomes the "Resume quality" part of the match score.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

ACTION_VERBS = frozenset(
    """
    accelerated achieved administered advanced advised analyzed analysed architected assembled audited authored
    automated boosted built calculated championed coached collaborated compiled completed conceived configured
    consolidated constructed contributed converted coordinated crafted created cultivated customized cut debugged
    decreased defined delivered deployed designed developed devised diagnosed directed documented doubled drafted
    drove earned eliminated enabled engineered enhanced established evaluated exceeded executed expanded expedited
    facilitated fixed forecasted formulated fostered founded generated grew guided halved headed identified
    implemented improved increased influenced initiated innovated instituted integrated introduced invented
    investigated launched led leveraged lowered maintained managed maximized measured mentored migrated minimized
    modeled modelled modernized monitored negotiated onboarded optimized optimised orchestrated organized
    outperformed overhauled oversaw owned partnered performed pioneered piloted planned presented prioritized
    produced programmed proposed prototyped published raised rebuilt reduced refactored redesigned reengineered
    re-architected resolved restructured revamped reviewed saved scaled secured shipped simplified solved
    spearheaded standardized streamlined strengthened structured supervised surpassed synthesized tested tracked
    trained transformed translated tripled troubleshot unified upgraded validated visualized won wrote
    """.split()
)

WEAK_PHRASES = (
    "responsible for", "duties included", "duties include", "worked on", "worked with", "helped with",
    "helped to", "assisted with", "assisted in", "tasked with", "involved in", "participated in", "in charge of",
    "was part of", "handled", "utilized",
)

BUZZWORDS = (
    "hard-working", "hardworking", "team player", "go-getter", "self-starter", "self starter", "results-driven",
    "results-oriented", "detail-oriented", "think outside the box", "synergy", "dynamic", "highly motivated",
    "fast learner", "quick learner", "go-to person", "rockstar", "ninja", "guru", "best of breed", "value add",
)

_METRIC_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|x\b|k\b|m\b|\+)|[$₹€£]\s?\d|\b\d{1,3}(?:,\d{3})+\b|"
    r"\b(?!(?:19|20)\d{2}\b)\d+\b|\b(?:doubled|tripled|halved|dozens|hundreds|thousands|millions)\b",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(r"\b(?:I|me|my|mine|myself)\b")


def first_word(text: str) -> str:
    match = re.match(r"\s*([A-Za-z][A-Za-z\-]*)", text)
    return match.group(1).lower() if match else ""


def starts_with_action_verb(text: str) -> bool:
    return first_word(text) in ACTION_VERBS


def weak_start(text: str) -> str | None:
    lowered = text.strip().lower()
    return next((p for p in WEAK_PHRASES if lowered.startswith(p)), None)


def has_metric(text: str) -> bool:
    return bool(_METRIC_RE.search(text))


@dataclass
class Check:
    id: str
    title: str
    status: str  # pass | warn | fail
    detail: str
    tip: str
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)


def _grade(value: float, good: float, ok: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "pass" if value >= good else "warn" if value >= ok else "fail"
    return "pass" if value <= good else "warn" if value <= ok else "fail"


def run_checks(
    *,
    word_total: int,
    contact: dict,
    sections: set[str],
    bullets: list[str],
    pronoun_text: str,
    full_text: str,
    has_dates: bool,
) -> list[Check]:
    checks: list[Check] = []
    add = checks.append

    # --- contact details
    add(Check("email", "Email address", "pass" if contact["email"] else "fail",
              contact["email"] or "No email address found.",
              "Put a professional email address at the top of your resume.", 2))
    add(Check("phone", "Phone number", "pass" if contact["phone"] else "warn",
              contact["phone"] or "No phone number found.",
              "Add a phone number so recruiters can reach you quickly.", 1))
    add(Check("linkedin", "LinkedIn profile", "pass" if contact["linkedin"] else "warn",
              contact["linkedin"] or "No LinkedIn URL found.",
              "Add your LinkedIn URL (linkedin.com/in/your-name).", 1))
    portfolio = contact["github"] or contact["website"]
    add(Check("portfolio", "Portfolio / GitHub", "pass" if portfolio else "warn",
              portfolio or "No GitHub or portfolio link found.",
              "Link to your GitHub or portfolio so reviewers can see your work.", 0.5))

    # --- structure
    core = {"experience", "education", "skills"}
    missing_core = sorted(core - sections)
    add(Check("sections", "Standard sections",
              "pass" if not missing_core else "warn" if len(missing_core) == 1 else "fail",
              "Found Experience, Education and Skills." if not missing_core
              else f"Missing or unrecognised: {', '.join(s.title() for s in missing_core)}.",
              "Use clear headings like 'Experience', 'Education' and 'Skills' - ATS software looks for them.", 2))
    add(Check("summary", "Summary section", "pass" if "summary" in sections else "warn",
              "Has a summary/profile." if "summary" in sections else "No summary or profile section.",
              "Open with a 2-3 line summary tailored to the role.", 0.5))

    # --- length
    length_status = (
        "pass" if 350 <= word_total <= 1000
        else "warn" if 250 <= word_total < 350 or 1000 < word_total <= 1300
        else "fail"
    )
    add(Check("length", "Length", length_status, f"{word_total} words.",
              "Aim for about 400-900 words (1-2 pages). Cut old or irrelevant detail; expand thin sections.", 1.5))

    # --- bullets & writing
    n = len(bullets)
    add(Check("bullets", "Achievement bullets", _grade(n, 5, 1), f"{n} bullet points found.",
              "Describe each role with 3-6 bullet points instead of paragraphs.", 1))
    if n:
        quantified = sum(has_metric(b) for b in bullets) / n
        add(Check("metrics", "Quantified results", _grade(quantified, 0.4, 0.2),
                  f"{round(quantified * 100)}% of bullets include a number.",
                  "Add numbers: % improvement, time saved, users, revenue, team size.", 2))
        action = sum(starts_with_action_verb(b) for b in bullets) / n
        add(Check("verbs", "Strong action verbs", _grade(action, 0.6, 0.35),
                  f"{round(action * 100)}% of bullets start with an action verb.",
                  "Start bullets with verbs like Built, Led, Reduced, Launched, Automated.", 2))
        long_bullets = sum(len(b.split()) > 35 for b in bullets)
        add(Check("long_bullets", "Concise bullets", _grade(long_bullets, 0, 2, higher_is_better=False),
                  f"{long_bullets} bullet(s) longer than 35 words.",
                  "Keep bullets to one or two lines - lead with the result.", 0.5))

    lowered = full_text.lower()
    weak = [p for p in WEAK_PHRASES if p in lowered]
    add(Check("weak_phrases", "Weak phrases", _grade(len(weak), 0, 2, higher_is_better=False),
              f"Found: {', '.join(repr(w) for w in weak)}." if weak else "No weak phrases found.",
              "Replace 'responsible for' / 'worked on' with what you actually achieved.", 1))
    buzz = [b for b in BUZZWORDS if b in lowered]
    add(Check("buzzwords", "Clichés & buzzwords", _grade(len(buzz), 1, 3, higher_is_better=False),
              f"Found: {', '.join(repr(b) for b in buzz)}." if buzz else "No clichés found.",
              "Show qualities through results instead of claiming them.", 0.5))
    pronouns = len(_PRONOUN_RE.findall(pronoun_text))
    add(Check("pronouns", "No first-person pronouns", _grade(pronouns, 1, 4, higher_is_better=False),
              f"{pronouns} use(s) of I / me / my.",
              "Write bullets without 'I' or 'my' - e.g. 'Built…' rather than 'I built…'.", 0.5))
    add(Check("dates", "Employment dates", "pass" if has_dates else "warn",
              "Date ranges found." if has_dates else "No date ranges (e.g. 'Jan 2021 - Present') found.",
              "Show start and end dates for each role so experience can be calculated.", 1))
    return checks


def quality_score(checks: list[Check]) -> int:
    value = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    total = sum(c.weight for c in checks)
    return round(100 * sum(c.weight * value[c.status] for c in checks) / total) if total else 0


def bullet_feedback(bullets: list[str], limit: int = 8) -> list[dict]:
    """Specific, rule-based tips for the weakest bullets."""
    results = []
    for bullet in bullets:
        issues, tips = [], []
        weak = weak_start(bullet)
        if weak:
            issues.append(f"Starts with “{weak}”")
            tips.append("Lead with a strong verb that shows ownership (Built, Led, Delivered, Improved).")
        elif not starts_with_action_verb(bullet):
            issues.append("Doesn't start with an action verb")
            tips.append("Start with what you did: “Designed…”, “Automated…”, “Reduced…”.")
        if not has_metric(bullet):
            issues.append("No measurable result")
            tips.append("Add a number - how much faster, cheaper, bigger, or how many users/people.")
        if len(bullet.split()) > 35:
            issues.append("Too long")
            tips.append("Trim to one or two lines; keep the result, cut the process.")
        if _PRONOUN_RE.search(bullet):
            issues.append("Uses first-person pronouns")
            tips.append("Drop 'I'/'my' - resume bullets are written without a subject.")
        if issues:
            results.append({"text": bullet, "issues": issues, "tips": tips, "severity": len(issues)})
    results.sort(key=lambda r: -r["severity"])
    return results[:limit]
