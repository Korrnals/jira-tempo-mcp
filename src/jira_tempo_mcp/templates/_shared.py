"""Shared extraction/formatting helpers for report templates.

These mirror the private helpers in :mod:`jira_tempo_mcp.report` so that
builtin and custom templates can reuse the same parsing logic without
duplicating it. Kept dependency-free (no httpx, no Config) so templates
stay pure and testable.
"""

from __future__ import annotations

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
    """Parse a Tempo startDate (ISO 8601) to a date object."""
    if not raw:
        return None
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return date.fromisoformat(raw)
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


__all__ = [
    "extract_comment",
    "extract_issue_key",
    "extract_seconds",
    "extract_worker",
    "format_date",
    "format_date_short",
    "month_ru",
    "parse_tempo_date",
    "week_range",
]
