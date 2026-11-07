"""Understanding a job description: which skills are must-haves vs nice-to-haves,
and what experience and education it asks for."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .experience import lowest_degree, years_mentioned
from .skills import SKILLS_BY_NAME, find_skills

# Order matters: "Preferred Qualifications" must be classified as preferred, not required.
_SECTION_RULES: list[tuple[str, re.Pattern]] = [
    ("preferred", re.compile(r"\b(?:preferred|nice[ -]to[ -]haves?|bonus|good[ -]to[ -]have|desired|desirable|pluses|extra credit)\b", re.I)),
    ("other", re.compile(r"\b(?:benefits|perks|about us|who we are|our company|compensation|salary|equal opportunity|why join|what we offer|about the company)\b", re.I)),
    ("required", re.compile(r"\b(?:requirements?|qualifications?|must[ -]haves?|what you(?:'ll)? (?:need|bring)|what we(?:'re| are) looking for|who you are|you have|you will have|required|minimum|basic|about you|skills)\b", re.I)),
    ("responsibilities", re.compile(r"\b(?:responsibilities|what you(?:'ll| will)? do|the role|your role|duties|day[ -]to[ -]day|in this role|you will)\b", re.I)),
]
_PREFERRED_LINE_RE = re.compile(
    r"\(preferred\)|\bpreferred\b|\bis a (?:big )?plus\b|\bnice to have\b|\bbonus\b|\ba plus\b|\bideally\b", re.I
)
_BULLETISH_RE = re.compile(r"^\s*(?:[•●▪◦‣∙■*·\-–—]|\d{1,2}[.)])\s+")


@dataclass
class JobSkill:
    name: str
    category: str
    importance: str  # required | preferred
    mentions: int
    soft: bool

    @property
    def weight(self) -> float:
        base = 1.0 if self.importance == "required" else 0.45
        if self.mentions >= 3:
            base *= 1.25
        return base * (0.5 if self.soft else 1.0)


@dataclass
class JobProfile:
    skills: list[JobSkill] = field(default_factory=list)
    years_required: int | None = None
    degree_required: str | None = None
    has_sections: bool = False
    keyword_text: str = ""  # the post without benefits / about-the-company sections


_SMALL_WORDS = {"a", "an", "and", "the", "to", "of", "for", "in", "on", "you", "we", "our", "your", "you'll", "do", "will", "have", "is"}


def _heading_kind(line: str) -> str | None:
    """Return the section kind if `line` looks like a section heading, else None.

    A heading is short and either ends with ':', is written in Title Case /
    CAPITALS, or consists mostly of the matched phrase ("Nice to have").
    This keeps lines such as "Kubernetes skills" from being read as headings.
    """
    stripped = line.strip().strip("#*_ ").strip()
    if not stripped or _BULLETISH_RE.match(line) or len(stripped) > 70 or len(stripped.split()) > 8:
        return None
    if stripped.endswith("."):
        return None
    words = [w for w in re.findall(r"[A-Za-z][\w'’]*", stripped) if w.lower() not in _SMALL_WORDS]
    title_case = bool(words) and sum(w[0].isupper() for w in words) / len(words) >= 0.7
    for kind, rule in _SECTION_RULES:
        match = rule.search(stripped)
        if not match:
            continue
        coverage = len(match.group(0)) / len(stripped.rstrip(":"))
        if stripped.endswith(":") or title_case or coverage >= 0.5:
            return kind
    return None


def classify_lines(text: str) -> list[tuple[int, int, str]]:
    """Split the job post into lines tagged required / preferred / responsibilities / other / general."""
    tagged: list[tuple[int, int, str]] = []
    current = "general"
    offset = 0
    for line in text.split("\n"):
        start, end = offset, offset + len(line)
        offset = end + 1
        kind_for_line = current
        heading = _heading_kind(line)
        if heading:
            current = heading
            kind_for_line = heading
        if kind_for_line in {"required", "responsibilities", "general"} and _PREFERRED_LINE_RE.search(line):
            kind_for_line = "preferred"
        tagged.append((start, end, kind_for_line))
    return tagged


def analyze_job(text: str) -> JobProfile:
    lines = classify_lines(text)
    profile = JobProfile(
        has_sections=any(kind != "general" for _, _, kind in lines),
        keyword_text="\n".join(text[s:e] for s, e, kind in lines if kind != "other"),
    )

    def kind_at(pos: int) -> str:
        for start, end, kind in lines:
            if start <= pos <= end:
                return kind
        return "general"

    for name, positions in find_skills(text).items():
        kinds = {kind_at(p) for p in positions}
        importance = "required" if kinds & {"required", "responsibilities", "general"} else "preferred"
        skill = SKILLS_BY_NAME[name]
        profile.skills.append(JobSkill(name, skill.category, importance, len(positions), skill.soft))

    order = {"required": 0, "preferred": 1}
    profile.skills.sort(key=lambda s: (order[s.importance], s.soft, -s.mentions, s.name))

    required_text = "\n".join(text[s:e] for s, e, kind in lines if kind not in {"preferred", "other"})
    years = years_mentioned(required_text)
    profile.years_required = max(years) if years else None
    profile.degree_required = lowest_degree(required_text)
    return profile
