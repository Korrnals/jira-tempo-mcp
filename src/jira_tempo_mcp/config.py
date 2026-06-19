"""Configuration loader — reads environment variables, never logs secrets.

Uses pydantic for validation. Secrets are masked in repr so accidental
print(config) does not leak credentials.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Load .env from project root (one level up from src/).
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

# --- Default section mapping for weekly reports ---
# Maps issue keys to report section titles. Can be overridden via
# REPORT_SECTION_MAP env var (JSON dict) or a JSON file at REPORT_SECTION_MAP_FILE.
# Default section mapping for weekly reports.
# Empty by default — users provide their own via REPORT_SECTION_MAP env var
# or REPORT_SECTION_MAP_FILE. See README for format.
DEFAULT_SECTION_MAP: dict[str, str] = {}

# Stable sections that always appear (in this order) if they have worklogs.
# Empty by default — users provide their own via REPORT_STABLE_ORDER env var.
DEFAULT_STABLE_ORDER: list[str] = []

# Non-issue sections (no issue key in the report line).
# Empty by default — users provide their own via REPORT_NON_ISSUE_SECTIONS env var.
DEFAULT_NON_ISSUE_SECTIONS: list[str] = []


class Config(BaseModel):
    """Runtime configuration loaded from environment.

    Secrets are held in this model and never logged. The __repr__ masks
    token fields so accidental print(config) does not leak credentials.
    """

    model_config = ConfigDict(frozen=True)

    jira_base_url: str = Field(min_length=1)
    jira_user: str = Field(min_length=1)
    jira_pat: str = Field(min_length=1)
    timezone: str = "Europe/Moscow"
    tempo_api_token: str | None = None  # falls back to jira_pat if empty
    log_level: str = "INFO"

    # Report configuration (M3, M4 — externalized from report.py).
    report_output_dir: str = Field(
        default="",
        description="Base directory for weekly reports. Empty = ./reports.",
    )
    author_display_name: str = Field(
        default="",
        description="Display name in report header. Empty = use jira_user.",
    )
    section_map: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SECTION_MAP),
        description="Maps issue keys to report section titles.",
    )
    stable_order: list[str] = Field(
        default_factory=lambda: list(DEFAULT_STABLE_ORDER),
        description="Issue keys that always appear in this order if they have worklogs.",
    )
    non_issue_sections: list[str] = Field(
        default_factory=lambda: list(DEFAULT_NON_ISSUE_SECTIONS),
        description="Sections without issue keys (planerki, Jira work).",
    )

    # HTTP timeout (m5 — configurable).
    http_timeout: float = Field(default=30.0, gt=0)

    def __repr__(self) -> str:  # pragma: no cover - safety guard
        return (
            f"Config(jira_base_url={self.jira_base_url!r}, "
            f"jira_user={self.jira_user!r}, "
            f"jira_pat=***, timezone={self.timezone!r}, "
            f"tempo_api_token={'***' if self.tempo_api_token else 'None'}, "
            f"log_level={self.log_level!r})"
        )

    @property
    def tempo_token(self) -> str:
        """Tempo auth token — uses TEMPO_API_TOKEN if set, else JIRA_PAT."""
        return self.tempo_api_token or self.jira_pat

    @property
    def tempo_api_base(self) -> str:
        return f"{self.jira_base_url.rstrip('/')}/rest/tempo-timesheets/4"

    @property
    def jira_api_base(self) -> str:
        return f"{self.jira_base_url.rstrip('/')}/rest/api/2"

    @property
    def report_author_header(self) -> str:
        """Author name for report header — uses author_display_name or jira_user."""
        return self.author_display_name or self.jira_user

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        upper = v.strip().upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {v!r}")
        return upper


def _load_section_map() -> dict[str, str]:
    """Load section map from env var (JSON) or file, falling back to default."""
    raw = os.getenv("REPORT_SECTION_MAP", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, TypeError):
            pass

    file_path = os.getenv("REPORT_SECTION_MAP_FILE", "").strip()
    if file_path:
        try:
            p = Path(file_path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, TypeError, OSError):
            pass

    return dict(DEFAULT_SECTION_MAP)


def load_config() -> Config:
    """Load configuration from environment. Raises if required vars are missing."""
    base_url = os.getenv("JIRA_BASE_URL", "").strip()
    user = os.getenv("JIRA_USER", "").strip()
    pat = os.getenv("JIRA_PAT", "").strip()
    tz = os.getenv("JIRA_TIMEZONE", "Europe/Moscow").strip()
    tempo_token = os.getenv("TEMPO_API_TOKEN", "").strip() or None
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    report_output_dir = os.getenv("REPORT_OUTPUT_DIR", "").strip()
    author_display_name = os.getenv("REPORT_AUTHOR_NAME", "").strip()
    http_timeout_str = os.getenv("JIRA_HTTP_TIMEOUT", "30.0").strip()

    try:
        http_timeout = float(http_timeout_str)
    except ValueError:
        http_timeout = 30.0

    # pydantic will validate non-empty constraints.
    return Config(
        jira_base_url=base_url,
        jira_user=user,
        jira_pat=pat,
        timezone=tz,
        tempo_api_token=tempo_token,
        log_level=log_level,
        report_output_dir=report_output_dir,
        author_display_name=author_display_name,
        section_map=_load_section_map(),
        http_timeout=http_timeout,
    )
