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

# Default directory for custom report templates (expanded at load time).
_DEFAULT_TEMPLATE_DIR = str(Path.home() / ".config" / "jira-tempo-mcp" / "templates")


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
    report_filename_prefix: str = Field(
        default="",
        description="Prefix for weekly report filenames. Empty = use jira_user.",
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

    # --- Team report rate-limiting (v0.2.0) ---
    tempo_max_concurrent_requests: int = Field(
        default=3,
        ge=1,
        description="Semaphore limit for concurrent Tempo requests in team reports.",
    )
    tempo_request_delay_ms: int = Field(
        default=100,
        ge=0,
        description="Delay (ms) between request batches in team reports.",
    )
    tempo_max_retries: int = Field(
        default=3,
        ge=0,
        description="Max retry attempts for HTTP 429 responses.",
    )
    report_team_output_dir: str = Field(
        default="",
        description="Output dir for team reports. Empty = use report_output_dir.",
    )

    # --- Custom report templates (v0.2.0) ---
    report_template: str = Field(
        default="default",
        description="Name of the template used by generate_weekly_report.",
    )
    report_template_path: str = Field(
        default="",
        description="Explicit path to a template file (overrides report_template).",
    )
    report_template_dir: str = Field(
        default="",
        description="Directory scanned for custom templates (.py / .j2).",
    )
    report_template_allow_py: bool = Field(
        default=False,
        description="Opt-in flag to load .py templates (code execution risk).",
    )

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

    @property
    def report_filename_header(self) -> str:
        """Filename prefix for weekly reports — uses report_filename_prefix or jira_user."""
        return self.report_filename_prefix or self.jira_user

    @property
    def team_output_dir(self) -> str:
        """Output dir for team reports — falls back to report_output_dir."""
        return self.report_team_output_dir or self.report_output_dir

    @property
    def template_dir_resolved(self) -> str:
        """Resolved custom template directory (default: ~/.config/jira-tempo-mcp/templates)."""
        return self.report_template_dir or _DEFAULT_TEMPLATE_DIR

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


def _load_json_list(env_var: str) -> list[str]:
    """Load a JSON list of strings from an env var.

    Returns an empty list if the var is unset, empty, or holds invalid JSON.
    Non-string items are coerced to str.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(item) for item in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _load_int(env_var: str, default: int) -> int:
    """Load an integer env var with a fallback."""
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _load_bool(env_var: str, default: bool) -> bool:
    """Load a boolean env var (1/0, true/false, yes/no)."""
    raw = os.getenv(env_var, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


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
    report_filename_prefix = os.getenv("REPORT_FILENAME_PREFIX", "").strip()
    stable_order = _load_json_list("REPORT_STABLE_ORDER")
    non_issue_sections = _load_json_list("REPORT_NON_ISSUE_SECTIONS")
    http_timeout_str = os.getenv("JIRA_HTTP_TIMEOUT", "30.0").strip()

    # v0.2.0 — team report rate-limiting + templates.
    tempo_max_concurrent = _load_int("TEMPO_MAX_CONCURRENT_REQUESTS", 3)
    tempo_request_delay_ms = _load_int("TEMPO_REQUEST_DELAY_MS", 100)
    tempo_max_retries = _load_int("TEMPO_MAX_RETRIES", 3)
    report_team_output_dir = os.getenv("REPORT_TEAM_OUTPUT_DIR", "").strip()
    report_template = os.getenv("REPORT_TEMPLATE", "default").strip() or "default"
    report_template_path = os.getenv("REPORT_TEMPLATE_PATH", "").strip()
    report_template_dir = os.getenv("REPORT_TEMPLATE_DIR", "").strip()
    report_template_allow_py = _load_bool("REPORT_TEMPLATE_ALLOW_PY", False)

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
        report_filename_prefix=report_filename_prefix,
        section_map=_load_section_map(),
        stable_order=stable_order,
        non_issue_sections=non_issue_sections,
        http_timeout=http_timeout,
        tempo_max_concurrent_requests=tempo_max_concurrent,
        tempo_request_delay_ms=tempo_request_delay_ms,
        tempo_max_retries=tempo_max_retries,
        report_team_output_dir=report_team_output_dir,
        report_template=report_template,
        report_template_path=report_template_path,
        report_template_dir=report_template_dir,
        report_template_allow_py=report_template_allow_py,
    )
