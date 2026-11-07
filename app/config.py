"""Settings read from environment variables (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader - real environment variables always take priority."""
    path = path or PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None = None
    coach_model: str = "claude-opus-5-5"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_resume_chars: int = 60_000
    max_job_chars: int = 30_000
    analyze_per_minute: int = 30
    coach_per_minute: int = 5
    trust_proxy: bool = False

    @property
    def coach_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None,
            coach_model=os.environ.get("COACH_MODEL", "").strip() or "claude-opus-5-5",
            analyze_per_minute=_int("ANALYZE_PER_MINUTE", 30),
            coach_per_minute=_int("COACH_PER_MINUTE", 5),
            trust_proxy=_bool("TRUST_PROXY", False),
        )
