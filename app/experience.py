"""Years-of-experience and degree detection (for both resumes and job posts)."""

from __future__ import annotations

import re
from datetime import date

# ------------------------------------------------------------------ degrees
DEGREE_LEVELS = {"associate": 1, "bachelor": 2, "master": 3, "phd": 4}
DEGREE_LABELS = {"associate": "Associate degree", "bachelor": "Bachelor's", "master": "Master's", "phd": "PhD"}

_DEGREE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("phd", re.compile(r"\bph\.?\s?d\b|\bdoctorate\b|\bdoctoral\b", re.I)),
    ("master", re.compile(r"\bmaster(?:'s|s)?\s+(?:degree|of|in)\b|\bmaster's\b|\bm\.?\s?tech\b|\bmba\b|\bmca\b|\bmsc\b|\bm\.\s?sc\b", re.I)),
    ("master", re.compile(r"\bM\.S\.|\bMS\s+(?:in|degree)\b|\bM\.E\.")),
    ("bachelor", re.compile(r"\bbachelor(?:'s|s)?\b|\bb\.?\s?tech\b|\bbsc\b|\bb\.\s?sc\b|\bbca\b|\bundergraduate degree\b|\b(?:4|four)[- ]year degree\b|\bdegree in\b", re.I)),
    ("bachelor", re.compile(r"\bB\.S\.|\bBS\s+(?:in|degree)\b|\bB\.E\.|\bBE\s+in\b|\bB\.A\.|\bBA\s+in\b")),
    ("associate", re.compile(r"\bassociate(?:'s)?\s+degree\b", re.I)),
]


def degree_levels(text: str) -> set[str]:
    return {level for level, pattern in _DEGREE_PATTERNS if pattern.search(text)}


def highest_degree(text: str) -> str | None:
    levels = degree_levels(text)
    return max(levels, key=DEGREE_LEVELS.__getitem__) if levels else None


def lowest_degree(text: str) -> str | None:
    levels = degree_levels(text)
    return min(levels, key=DEGREE_LEVELS.__getitem__) if levels else None


# ------------------------------------------------------- years required (JD)
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)\b", re.IGNORECASE
)


def years_mentioned(text: str) -> list[int]:
    """Lower bounds of 'N+ years ... experience' phrases in `text`."""
    found = []
    for m in _YEARS_RE.finditer(text):
        window = text[max(0, m.start() - 60) : m.end() + 60].lower()
        if "experience" not in window or "old" in text[m.end() : m.end() + 6].lower():
            continue
        value = int(m.group(1))
        if 0 < value <= 25:
            found.append(value)
    return found


# ------------------------------------------------ years worked (resume dates)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE = rf"(?:{_MONTH}\.?\s*,?\s*(?:19|20)\d{{2}}|\d{{1,2}}\s*/\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_RANGE_RE = re.compile(
    rf"({_DATE})\s*(?:-|–|—|to|till|until)\s*({_DATE}|present|current|now|today|ongoing|date)", re.IGNORECASE
)


def _parse_date(token: str, today: date, is_end: bool) -> tuple[int, int] | None:
    token = token.strip().lower()
    if token in {"present", "current", "now", "today", "ongoing", "date"}:
        return today.year, today.month
    m = re.match(r"([a-z]+)\.?\s*,?\s*(\d{4})", token)
    if m:
        return int(m.group(2)), _MONTHS.get(m.group(1)[:3], 6)
    m = re.match(r"(\d{1,2})\s*/\s*(\d{4})", token)
    if m:
        month = int(m.group(1))
        return int(m.group(2)), month if 1 <= month <= 12 else 6
    m = re.match(r"(\d{4})", token)
    if m:
        return int(m.group(1)), 6  # year only: assume mid-year
    return None


def date_ranges(text: str, today: date | None = None) -> list[tuple[int, int]]:
    """All employment-style date ranges in `text` as (start, end) month indexes."""
    today = today or date.today()
    ranges = []
    for m in _RANGE_RE.finditer(text):
        start = _parse_date(m.group(1), today, False)
        end = _parse_date(m.group(2), today, True)
        if not start or not end:
            continue
        s = start[0] * 12 + start[1]
        e = end[0] * 12 + end[1]
        if 1970 <= start[0] <= today.year and s <= e <= today.year * 12 + today.month + 1 and e - s <= 50 * 12:
            ranges.append((s, e))
    return ranges


def total_years(ranges: list[tuple[int, int]]) -> float:
    """Sum the ranges after merging overlaps (two jobs at once count once)."""
    if not ranges:
        return 0.0
    merged: list[list[int]] = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum(e - s for s, e in merged)
    return round(months / 12, 1)


_CLAIM_RE = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|industry\s+|hands-on\s+|relevant\s+|work\s+)?experience",
    re.IGNORECASE,
)


def claimed_years(text: str) -> int | None:
    values = [int(v) for v in _CLAIM_RE.findall(text) if 0 < int(v) <= 40]
    return max(values) if values else None
