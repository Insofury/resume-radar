"""Text helpers shared by the analysers: normalisation, tokens, stemming and
keyword extraction. Everything here is plain Python - no NLP downloads needed."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

# Characters that commonly start a bullet line in resumes (after PDF extraction).
BULLET_GLYPHS = "•●▪◦‣∙■□➢➤►✓✔◆◇○*·"
BULLET_RE = re.compile(rf"^\s*(?:[{re.escape(BULLET_GLYPHS)}]|[-–—](?=\s)|\(?\d{{1,2}}[.)](?=\s))\s*")

WORD_RE = re.compile(r"[a-z][a-z'\-]*[a-z]")

STOPWORDS = frozenset(
    """
    a about above after again against all also am an and any are aren't as at be because been before being below
    between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each
    either etc few for from further had hadn't has hasn't have haven't having he her here hers herself him himself
    his how however i if in into is isn't it it's its itself just let's me more most must mustn't my myself no nor
    not now of off on once only or other ought our ours ourselves out over own per same shall she should shouldn't
    so some such than that that's the their theirs them themselves then there there's these they they're this
    those through to too under until up upon us very via was wasn't we we're were weren't what what's when where
    which while who whom why will with within without won't would wouldn't yet you you'll you're your yours
    yourself yourselves e.g i.e
    """.split()
)

# Words that appear in almost every job post and say nothing about the actual job.
GENERIC_JOB_WORDS = frozenset(
    """
    ability able abilities across additional apply applicant applicants application applications area areas
    based benefit benefits best bonus build candidate candidates career careers company companies competitive
    compensation culture day days degree description desired different diverse diversity employee employees
    employer employment environment equal equivalent excellent exceptional excited exciting experience
    experienced experiences field fast-paced flexible full full-time good great grow growing growth help
    highly hire hiring hybrid ideal ideally impact include includes including insurance job join key knowledge
    level life location looking love make makes making minimum mission new office offer offers opportunity
    opportunities organization paced part passion passionate people perks plus position preferred proficiency
    proficient qualification qualifications related relevant remote required requirement requirements
    responsibilities responsibility role roles salary similar skill skilled skills solid strong success
    successful support team teams time today understanding using value values want way well work working
    world year years etc ensure etc. thrive thriving join us we're you'll who're kind type types various range
    must-have nice-to-have nice have preferably familiarity familiar exposure hands-on demonstrated proven
    track record self excellent including within plus
    behind closely keep operate improve own lead drive deliver create develop maintain write manage define
    collaborate partner enable provide perform need needs like every each real expert deep large small complex
    multiple daily effectively quickly closely ensure across able bring brings build building built design
    designing improving owning leading driving delivering creating developing maintaining writing managing
    bachelor bachelor's master master's degree phd computer science
    """.split()
)


def proper_nouns(text: str) -> set[str]:
    """Words that only ever appear capitalised (company names, heading words, bullet-leading verbs)."""
    capitalised = {w.lower() for w in re.findall(r"\b[A-Z][a-z][a-z'\-]*\b", text)}
    lower = set(re.findall(r"\b[a-z][a-z'\-]+\b", text))
    return capitalised - lower


def normalize_text(text: str) -> str:
    """Clean up text extracted from PDFs/DOCX so the analysers see tidy lines."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace("​", "")
    lines = [line.rstrip() for line in text.split("\n")]

    # PDF extraction often puts a bullet glyph on its own line - glue it to the next line.
    merged: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and len(stripped) == 1 and stripped in BULLET_GLYPHS and i + 1 < len(lines):
            merged.append(f"• {lines[i + 1].strip()}")
            i += 2
            continue
        merged.append(lines[i])
        i += 1

    text = "\n".join(merged)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def words(text: str) -> list[str]:
    """Lower-case word tokens (letters, inner apostrophes/hyphens)."""
    return WORD_RE.findall(text.lower())


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w[\w'+#.\-]*\b", text))


def stem(word: str) -> str:
    """A tiny suffix-stripping stemmer: manage/managed/managing -> 'manag'."""
    w = word.lower()
    if len(w) <= 3:
        return w
    for suffix, replacement, min_len in (
        ("ations", "", 7),
        ("ation", "", 6),
        ("ments", "", 6),
        ("ment", "", 6),
        ("ings", "", 6),
        ("ing", "", 5),
        ("ies", "y", 5),
        ("ied", "y", 5),
        ("ed", "", 5),
        ("es", "", 5),
        ("s", "", 4),
    ):
        if w.endswith(suffix) and len(w) >= min_len and not (suffix == "s" and w.endswith("ss")):
            w = w[: -len(suffix)] + replacement
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def is_content_word(word: str) -> bool:
    return len(word) >= 3 and word not in STOPWORDS and word not in GENERIC_JOB_WORDS and not word.isdigit()


def extract_keywords(text: str, exclude: set[str] | None = None, top_n: int = 20) -> list[dict]:
    """Return the job post's most repeated meaningful terms (unigrams and bigrams).

    `exclude` holds lower-cased terms to skip (e.g. skills already counted).
    Each item: {"term": surface form, "stems": tuple of stems, "count": n}.
    """
    exclude = (exclude or set()) | proper_nouns(text)
    exclude_stems = {stem(w) for term in exclude for w in term.split()}

    unigram_counts: Counter[str] = Counter()
    surface: dict[str, Counter[str]] = {}
    bigram_counts: Counter[tuple[str, str]] = Counter()
    bigram_surface: dict[tuple[str, str], Counter[str]] = {}

    # Work sentence by sentence so bigrams never cross punctuation.
    for chunk in re.split(r"[\n.;:!?()\[\],/|•]+", text):
        tokens = words(chunk)
        prev: str | None = None
        for token in tokens:
            if not is_content_word(token) or token in exclude:
                prev = None
                continue
            s = stem(token)
            if s in exclude_stems:
                prev = None
                continue
            unigram_counts[s] += 1
            surface.setdefault(s, Counter())[token] += 1
            if prev is not None:
                key = (stem(prev), s)
                bigram_counts[key] += 1
                bigram_surface.setdefault(key, Counter())[f"{prev} {token}"] += 1
            prev = token

    items: list[dict] = []
    used_stems: set[str] = set()
    for key, count in bigram_counts.most_common():
        if count < 2:
            break
        items.append({"term": bigram_surface[key].most_common(1)[0][0], "stems": key, "count": count})
        used_stems.update(key)

    min_count = 2 if sum(unigram_counts.values()) > 120 else 1
    for s, count in unigram_counts.most_common():
        if count < min_count:
            break
        if s in used_stems:
            continue
        items.append({"term": surface[s].most_common(1)[0][0], "stems": (s,), "count": count})

    items.sort(key=lambda item: (-item["count"], -len(item["stems"]), item["term"]))
    return items[:top_n]


def stem_sequence(text: str) -> str:
    """Space-joined stems with padding, for fast phrase containment checks."""
    return " " + " ".join(stem(w) for w in words(text)) + " "


def contains_stems(stemmed_text: str, stems: tuple[str, ...]) -> bool:
    return f" {' '.join(stems)} " in stemmed_text
