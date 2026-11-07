"""Optional AI coach powered by Claude.

When ANTHROPIC_API_KEY is set, the coach rewrites weak bullet points for the
target job and drafts a tailored summary. It uses structured outputs so the reply
is always valid JSON matching COACH_SCHEMA. Without a key the rest of the app
works normally and this feature is simply hidden.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("resumeradar.coach")

# Server-side refusal fallback ("default" form): if a safety classifier declines
# the request, the API retries it on a recommended fallback model in the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"})

SYSTEM_PROMPT = """\
You are an expert resume coach and technical recruiter. You help candidates tailor \
their resume to a specific job description.

Rules:
- Never invent employers, skills, tools, dates or numbers the resume doesn't support. \
Where a metric would make a bullet stronger but isn't given, insert a bracketed \
placeholder such as [X%] or [N users] for the candidate to fill in.
- Bullets start with a strong past-tense action verb, have no first-person pronouns, \
lead with the result, and stay under about 30 words.
- Use the job description's own terminology where the candidate's experience truthfully matches it.
- Be specific and practical. Plain, confident English - no buzzwords."""

COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tailored_summary": {
            "type": "string",
            "description": "A 2-3 sentence professional summary tailored to this job.",
        },
        "bullet_rewrites": {
            "type": "array",
            "description": "Up to 5 of the resume's weakest bullets rewritten for this job.",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "improved": {"type": "string"},
                    "why": {"type": "string", "description": "One short sentence on what changed."},
                },
                "required": ["original", "improved", "why"],
                "additionalProperties": False,
            },
        },
        "top_tips": {
            "type": "array",
            "description": "3-5 short, specific tips to improve the match for this job.",
            "items": {"type": "string"},
        },
    },
    "required": ["tailored_summary", "bullet_rewrites", "top_tips"],
    "additionalProperties": False,
}


class BulletRewrite(BaseModel):
    original: str
    improved: str
    why: str


class CoachResult(BaseModel):
    tailored_summary: str
    bullet_rewrites: list[BulletRewrite]
    top_tips: list[str]


class CoachError(RuntimeError):
    """Message is safe to show to the user."""


def build_prompt(resume_text: str, job_text: str, missing_skills: list[str], weak_bullets: list[str]) -> str:
    focus = "\n".join(f"- {b}" for b in weak_bullets[:8]) or "- (choose the weakest bullets yourself)"
    missing = ", ".join(missing_skills[:15]) or "none detected"
    return f"""\
<job_description>
{job_text}
</job_description>

<resume>
{resume_text}
</resume>

<analysis>
Skills the job mentions that the resume doesn't show: {missing}
Bullets our checker flagged as weak:
{focus}
</analysis>

Tailor this resume to the job: rewrite up to 5 of the weakest bullets, write a tailored \
summary, and give 3-5 concrete tips. Only mention a missing skill in a rewrite if the \
resume already shows evidence of it; otherwise suggest it as a tip ("if you have used X, add...")."""


def _describe(exc: Exception) -> str:
    if isinstance(exc, anthropic.AuthenticationError):
        return "The server's Anthropic API key was rejected."
    if isinstance(exc, anthropic.RateLimitError):
        return "The AI coach is busy right now. Please try again in a minute."
    if isinstance(exc, anthropic.BadRequestError):
        return "The AI coach couldn't process this resume. Try shortening it."
    if isinstance(exc, anthropic.APIStatusError):
        return "The AI service is temporarily unavailable. Please try again shortly."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach the AI service. Please try again."
    return "The AI coach failed unexpectedly."


class Coach:
    def __init__(self, api_key: str, model: str = "claude-opus-5-5", client: Any | None = None):
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=180.0)
        self.model = model

    def request_params(self, prompt: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": COACH_SCHEMA}},
        }
        if self.model in FALLBACK_MODELS:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    async def review(
        self, resume_text: str, job_text: str, missing_skills: list[str], weak_bullets: list[str]
    ) -> CoachResult:
        prompt = build_prompt(resume_text, job_text, missing_skills, weak_bullets)
        try:
            response = await self._client.beta.messages.create(**self.request_params(prompt))
        except anthropic.APIError as exc:
            logger.warning("Coach API error: %s", exc)
            raise CoachError(_describe(exc)) from exc

        if response.stop_reason == "refusal":
            raise CoachError("The AI coach declined to review this content.")
        if response.stop_reason == "max_tokens":
            raise CoachError("The AI coach's answer was cut off. Please try again.")

        # Only text after the last fallback marker belongs to the final answer.
        blocks = list(response.content)
        last_fallback = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
        text = "".join(b.text for b in blocks[last_fallback + 1 :] if b.type == "text")
        try:
            result = CoachResult.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Coach returned unexpected output: %s", exc)
            raise CoachError("The AI coach returned an unexpected answer. Please try again.") from exc
        result.bullet_rewrites = result.bullet_rewrites[:5]
        result.top_tips = result.top_tips[:5]
        return result
