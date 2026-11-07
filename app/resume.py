"""Understanding the structure of a resume: sections, contact details and bullets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutils import BULLET_RE

SECTION_HEADINGS: dict[str, str] = {
    "summary": r"(?:professional\s+|career\s+|executive\s+)?(?:summary|profile|objective)|about\s+me",
    "experience": r"(?:work|professional|employment|relevant|industry)?\s*(?:experience|history)|employment|internships?|career\s+history",
    "education": r"education(?:al)?(?:\s+background)?|academic\s+(?:background|qualifications|history)|academics",
    "skills": r"(?:technical\s+|core\s+|key\s+|relevant\s+)?(?:skills|competencies|expertise)(?:\s*(?:&|and)\s*\w+)?|technologies|tech\s+stack|tools(?:\s*(?:&|and)\s*technologies)?",
    "projects": r"(?:personal\s+|academic\s+|key\s+|selected\s+|side\s+)?projects",
    "certifications": r"certifications?(?:\s*(?:&|and)\s*\w+)?|licenses?|courses|training",
    "achievements": r"achievements|awards(?:\s*(?:&|and)\s*\w+)?|honou?rs|accomplishments",
}
_HEADING_RES = {kind: re.compile(rf"\s*(?:{pat})\s*:?\s*", re.IGNORECASE) for kind, pat in SECTION_HEADINGS.items()}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().\-]{8,}\d)(?!\w)")
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-%]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"github\.com/[\w\-]+", re.IGNORECASE)
URL_RE = re.compile(r"(?:https?://|www\.)[\w\-.]+\.[a-z]{2,}[^\s]*", re.IGNORECASE)


@dataclass
class ResumeStructure:
    lines: list[str]
    sections: dict[str, list[tuple[int, int]]] = field(default_factory=dict)  # kind -> [(start, end)] line ranges

    def has(self, kind: str) -> bool:
        return kind in self.sections

    def text_of(self, *kinds: str) -> str:
        chunks = []
        for kind in kinds:
            for start, end in self.sections.get(kind, []):
                chunks.append("\n".join(self.lines[start:end]))
        return "\n".join(chunks)


def heading_kind(line: str) -> str | None:
    stripped = line.strip().strip("#*_ ").strip()
    if not stripped or len(stripped) > 45 or len(stripped.split()) > 5:
        return None
    for kind, pattern in _HEADING_RES.items():
        if pattern.fullmatch(stripped):
            return kind
    return None


def parse_structure(text: str) -> ResumeStructure:
    lines = text.split("\n")
    headings = [(i, kind) for i, line in enumerate(lines) if (kind := heading_kind(line))]
    structure = ResumeStructure(lines=lines)
    for idx, (line_no, kind) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        structure.sections.setdefault(kind, []).append((line_no + 1, end))
    return structure


def contact_info(text: str) -> dict[str, str | None]:
    phone = None
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        # skip date ranges like 2019 - 2022 that look numeric
        if 10 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)\d{2}", digits):
            phone = m.group(1).strip()
            break
    email = EMAIL_RE.search(text)
    linkedin = LINKEDIN_RE.search(text)
    github = GITHUB_RE.search(text)
    website = next((u.group(0) for u in URL_RE.finditer(text) if "linkedin" not in u.group(0).lower()), None)
    return {
        "email": email.group(0) if email else None,
        "phone": phone,
        "linkedin": linkedin.group(0) if linkedin else None,
        "github": github.group(0) if github else None,
        "website": website,
    }


def extract_bullets(structure: ResumeStructure) -> list[str]:
    """Achievement bullets from experience/projects (or the whole resume if no sections)."""
    if structure.has("experience") or structure.has("projects"):
        ranges = structure.sections.get("experience", []) + structure.sections.get("projects", [])
        candidate_lines = [line for start, end in sorted(ranges) for line in structure.lines[start:end]]
    else:
        candidate_lines = structure.lines

    bullets: list[str] = []
    marked = False
    for line in candidate_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if BULLET_RE.match(stripped):
            marked = True
            bullets.append(BULLET_RE.sub("", stripped, count=1).strip())
        elif bullets and marked and stripped[0].islower():
            bullets[-1] = f"{bullets[-1]} {stripped}"  # wrapped continuation line
    bullets = [b for b in bullets if len(b.split()) >= 3]

    if not bullets:
        # No bullet glyphs (e.g. pasted text): use sentence-like lines that start with a verb-ish word.
        from .checks import starts_with_action_verb, weak_start

        for line in candidate_lines:
            stripped = line.strip()
            if len(stripped.split()) >= 6 and (starts_with_action_verb(stripped) or weak_start(stripped)):
                bullets.append(stripped)
    return bullets
