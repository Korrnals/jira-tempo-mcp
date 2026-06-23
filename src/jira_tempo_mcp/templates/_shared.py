"""Shared extraction/formatting helpers for report templates.

These mirror the private helpers in :mod:`jira_tempo_mcp.report` so that
builtin and custom templates can reuse the same parsing logic without
duplicating it. Kept dependency-free (no httpx, no Config) so templates
stay pure and testable.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any


def week_range(target: date) -> tuple[date, date]:
    """Return (monday, friday) of the ISO week containing ``target``."""
    monday = target - timedelta(days=target.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def format_date(d: date) -> str:
    """Format a date as DD.MM.YYYY (report header style)."""
    return d.strftime("%d.%m.%Y")


def format_date_short(d: date) -> str:
    """Format a date as DDMMYY (filename style)."""
    return d.strftime("%d%m%y")


def month_ru(month: int) -> str:
    """Map month number to Russian lowercase month name (for folder name)."""
    names = [
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    ]
    return names[month - 1]


def parse_tempo_date(raw: str | None) -> date | None:
    """Parse a Tempo date string to a date object.

    Handles multiple formats:
    - ISO 8601 with T: "2026-06-15T00:00:00.000" or "2026-06-15T00:00:00Z"
    - Tempo with space: "2026-06-15 00:00:00.000"
    - Pure date: "2026-06-15"
    """
    if not raw:
        return None
    try:
        # Tempo uses space separator instead of T — normalize to T.
        normalized = raw.replace(" ", "T") if " " in raw and "T" not in raw else raw
        if "T" in normalized:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        return date.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def extract_comment(worklog: dict[str, Any]) -> str:
    """Extract the comment text from a Tempo worklog object."""
    comment = worklog.get("comment")
    if isinstance(comment, str):
        return comment.strip()
    if isinstance(comment, dict):
        return str(comment.get("content", "")).strip()
    return ""


def extract_issue_key(worklog: dict[str, Any]) -> str | None:
    """Extract issue key from a Tempo worklog object."""
    key = worklog.get("issueKey")
    if key:
        return str(key)
    issue = worklog.get("issue")
    if isinstance(issue, dict):
        k = issue.get("key")
        if k:
            return str(k)
    return None


def extract_seconds(worklog: dict[str, Any]) -> int:
    """Extract time spent in seconds from a Tempo worklog object."""
    seconds = worklog.get("timeSpentSeconds")
    if isinstance(seconds, int):
        return seconds
    return 0


def extract_worker(worklog: dict[str, Any]) -> str | None:
    """Extract worker/author key from a Tempo worklog object."""
    worker = worklog.get("authorAccountId") or worklog.get("workerKey")
    if worker:
        return str(worker)
    author = worklog.get("author")
    if isinstance(author, dict):
        key = author.get("key") or author.get("accountId")
        if key:
            return str(key)
    return None


_WS_RE = re.compile(r"\s+")


def normalize_comment(comment: str | None) -> str:
    """Normalize a worklog comment for grouping.

    - Strips leading/trailing whitespace.
    - Replaces newlines with spaces.
    - Collapses multiple whitespace characters into a single space.
    - Returns an empty string for ``None`` or empty input.
    """
    if not comment:
        return ""
    text = str(comment).replace("\r", " ").replace("\n", " ")
    text = _WS_RE.sub(" ", text)
    return text.strip()


def group_worklogs_by_comment(
    worklogs: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    """Group worklogs by normalized comment and sum their time.

    Worklogs with identical (after normalization) comments are collapsed into
    a single entry, with their ``timeSpentSeconds`` summed. Worklogs with empty
    comments are grouped together under ``""``.

    Returns a list of ``(comment, total_seconds)`` tuples sorted by
    ``total_seconds`` descending (ties broken alphabetically by comment for
    deterministic output).
    """
    totals: dict[str, int] = {}
    for wl in worklogs:
        comment = normalize_comment(extract_comment(wl))
        totals[comment] = totals.get(comment, 0) + extract_seconds(wl)
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))


def truncate_text(text: str, max_len: int) -> str:
    """Truncate text to max_len chars, appending the ellipsis if truncated.

    Newlines are replaced with spaces and whitespace is collapsed before
    truncation so table cells stay on one line.
    """
    if not text:
        return ""
    cleaned = str(text).replace("\r", " ").replace("\n", " ")
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "\u2026"


def md_escape_cell(text: str) -> str:
    """Escape pipe characters for safe use in Markdown table cells.

    Returns an em-dash for empty/None values so tables do not have blank cells.
    """
    if not text:
        return "\u2014"
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", "")


__all__ = [
    "extract_comment",
    "extract_issue_key",
    "extract_seconds",
    "extract_worker",
    "format_date",
    "format_date_short",
    "group_worklogs_by_comment",
    "md_escape_cell",
    "month_ru",
    "normalize_comment",
    "parse_tempo_date",
    "truncate_text",
    "week_range",
]
