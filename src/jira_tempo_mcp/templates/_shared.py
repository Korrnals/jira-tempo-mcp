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


def group_worklogs_by_comment_raw(
    worklogs: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    """Group worklogs by normalized comment but return the RAW comment.

    Grouping/summation is identical to :func:`group_worklogs_by_comment` —
    worklogs whose comments are equal after normalization are merged and their
    ``timeSpentSeconds`` are summed. The difference is the returned comment:
    this function yields the *first-seen original* comment text (with its
    newlines and bullet structure preserved) instead of the flattened,
    whitespace-collapsed grouping key.

    This separates two concerns that used to be conflated:
    - the *grouping key* (normalized, single-line) drives summation;
    - the *render/serialization payload* (raw, multi-line) preserves the
      structure that the TXT/MD/JSON render paths need.

    Returns a list of ``(raw_comment, total_seconds)`` tuples sorted by
    ``total_seconds`` descending (ties broken alphabetically by the normalized
    key for deterministic output).
    """
    totals: dict[str, int] = {}
    raw_repr: dict[str, str] = {}
    for wl in worklogs:
        raw = extract_comment(wl)
        key = normalize_comment(raw)
        totals[key] = totals.get(key, 0) + extract_seconds(wl)
        if key not in raw_repr:
            raw_repr[key] = raw
    ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(raw_repr[key], secs) for key, secs in ordered]


# Leading bullet markers recognised at the start of a comment line. Covers
# ASCII (+, -, *), the unicode bullet (•), en/em dashes (–, —), and numbered
# markers (``1.`` / ``1)``). The marker must be followed by whitespace or the
# end of the line so that hyphenated words ("re-deploy") are never mangled.
_BULLET_MARKER_RE = re.compile(r"^[\t ]*(?:[-+*\u2022\u2013\u2014]|\d+[.)])(?=[\t ]|$)[\t ]*")


def strip_bullet_marker(line: str) -> str:
    """Strip leading bullet marker(s) from a single line.

    Removes any leading ``+``, ``-``, ``*``, ``•``, ``–``, ``—`` or numbered
    (``1.`` / ``1)``) marker, together with the surrounding whitespace. Applied
    repeatedly so a doubly-marked source line (``"+ + text"``) collapses to a
    single clean ``"text"``. Returns the line unchanged (minus outer
    whitespace) when no marker is present.
    """
    if not line:
        return ""
    text = line
    while True:
        stripped = _BULLET_MARKER_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return text.strip()


def split_comment_lines(comment: str | None) -> list[str]:
    """Split a worklog comment into clean, marker-free action items.

    Each physical line of the comment becomes one item, with its leading bullet
    marker stripped (see :func:`strip_bullet_marker`). Empty lines are dropped.
    A single-line comment yields a one-element list; an empty/blank comment
    yields an empty list.

    This is the single source of truth for turning a (possibly multi-line)
    comment into render-ready sub-items, so no render site re-implements bullet
    parsing or accidentally re-adds a marker.
    """
    if not comment:
        return []
    normalized = str(comment).replace("\r\n", "\n").replace("\r", "\n")
    items: list[str] = []
    for raw_line in normalized.split("\n"):
        cleaned = strip_bullet_marker(raw_line)
        if cleaned:
            items.append(cleaned)
    return items


def render_comment_lines(
    comment: str | None,
    *,
    indent: str,
    marker: str,
    time_human: str | None = None,
) -> list[str]:
    """Render a comment as one or more plain-text bullet lines.

    Splits ``comment`` into action items (see :func:`split_comment_lines`),
    prefixes each with ``indent`` + ``marker`` + space, and attaches the
    ``time_human`` suffix (``" — {time}"``) to the LAST item only so a grouped
    multi-line comment reports its summed time exactly once.

    Returns an empty list for empty comments — callers decide how to render the
    "no comment" case (e.g. ``"{time} отработано"``).
    """
    parts = split_comment_lines(comment)
    if not parts:
        return []
    last = len(parts) - 1
    lines: list[str] = []
    for i, part in enumerate(parts):
        if i == last and time_human:
            lines.append(f"{indent}{marker} {part} \u2014 {time_human}")
        else:
            lines.append(f"{indent}{marker} {part}")
    return lines


def render_comment_cell(comment: str | None, *, marker: str = "\u2022", max_len: int = 80) -> str:
    """Render a comment as a single, table-safe Markdown cell string.

    Single-action comments render as the plain (truncated, pipe-escaped) text.
    Multi-action comments render each item on its own visual line using ``<br>``
    (which keeps the surrounding Markdown table parseable — no raw newlines or
    unescaped pipes leak into the cell) prefixed by a unified ``marker``.

    Empty comments render as an em-dash, matching :func:`md_escape_cell`.
    """
    parts = split_comment_lines(comment)
    if not parts:
        return "\u2014"
    if len(parts) == 1:
        return md_escape_cell(truncate_text(parts[0], max_len))
    return "<br>".join(f"{marker} {md_escape_cell(truncate_text(p, max_len))}" for p in parts)


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
    "group_worklogs_by_comment_raw",
    "md_escape_cell",
    "month_ru",
    "normalize_comment",
    "parse_tempo_date",
    "render_comment_cell",
    "render_comment_lines",
    "split_comment_lines",
    "strip_bullet_marker",
    "truncate_text",
    "week_range",
]
