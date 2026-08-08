"""Shared helpers for report output (weekly / team / tasks).

These helpers previously lived duplicated across ``report.py``,
``tasks_report.py`` and ``team_report.py``. Centralising them here keeps the
output-directory resolution, worklog sort order, and file-write newlines
consistent across every report kind.

Public API
----------
- :func:`resolve_report_base_dir` — base output dir for reports (team or weekly).
- :func:`sort_worklogs_by_issue` — stable sort: issue key asc, seconds desc.
- :func:`write_report_file` — write a report with UTF-8 + LF newlines.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import Config
from .templates._shared import extract_issue_key, extract_seconds

logger = logging.getLogger(__name__)

# Default base directory for report output when REPORT_OUTPUT_DIR env is not set.
_DEFAULT_REPORT_DIR = str(Path.home() / ".mcp" / "jira-tempo-mcp" / "reports")


def resolve_report_base_dir(config: Config, *, team: bool = False) -> Path:
    """Resolve the base output directory for reports.

    ``team=True`` prefers ``REPORT_TEAM_OUTPUT_DIR`` (falling back to
    ``REPORT_OUTPUT_DIR`` via :attr:`Config.team_output_dir`); otherwise the
    weekly-report root ``REPORT_OUTPUT_DIR`` is used. Either way, when the
    chosen root is empty the default ``~/.mcp/jira-tempo-mcp/reports`` applies.
    """
    raw = (config.team_output_dir if team else config.report_output_dir) or _DEFAULT_REPORT_DIR
    return Path(raw)


def sort_worklogs_by_issue(worklogs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort worklogs by issue key asc, then by seconds desc within issue.

    Uses the canonical :func:`extract_issue_key` and :func:`extract_seconds`
    helpers from :mod:`templates._shared` so the order is identical in every
    report kind. Worklogs without an issue key sort first (empty string).
    """
    return sorted(worklogs, key=lambda wl: (extract_issue_key(wl) or "", -extract_seconds(wl)))


def write_report_file(path: Path, text: str) -> None:
    """Write report ``text`` to ``path`` with UTF-8 encoding and LF newlines.

    ``newline="\\n"`` forces consistent line endings on every platform
    (Windows default would otherwise translate to CRLF, corrupting report
    diffs and downstream plain-text consumers).
    """
    path.write_text(text, encoding="utf-8", newline="\n")
