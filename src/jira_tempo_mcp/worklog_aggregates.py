"""list_worklogs aggregation sections (P5, backlog wave 2026-10-30) — read-only.

Pure functions only: fetching stays in the server handler and the Tempo
client surface is untouched — aggregation runs over the SAME rows the
handler already renders. Default behaviour (``group_by="none"`` +
``include_totals=false``) keeps the ``list_worklogs`` response
byte-identical to the pre-P5 output (guard: the existing default-output
tests in ``tests/test_bugs_and_ux.py`` are unchanged).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, NamedTuple

from .templates._shared import parse_tempo_date
from .utils import format_seconds_to_human

GROUP_BY_VALUES = ("none", "issue", "day")


class WorklogEntry(NamedTuple):
    """Minimal per-worklog data the handler extracts while rendering rows."""

    issue_key: str
    day: date | None  # None when the started date is unparseable
    seconds: int


def extract_entries(worklogs: list[dict[str, Any]]) -> list[WorklogEntry]:
    """Extract aggregate-ready entries from raw Tempo worklog dicts.

    Mirrors the row-extraction logic in ``_handle_list_worklogs`` (same
    fallback chain for the issue key and the started date) so the
    aggregates and the rendered rows always agree.
    """
    entries: list[WorklogEntry] = []
    for wl in worklogs:
        key = wl.get("issueKey")
        if not key:
            issue = wl.get("issue")
            key = issue.get("key", "?") if isinstance(issue, dict) else "?"
        day = parse_tempo_date(wl.get("started") or wl.get("startDate"))
        seconds = wl.get("timeSpentSeconds", 0)
        entries.append(WorklogEntry(str(key), day, int(seconds) if seconds else 0))
    return entries


def _hours_by_issue(entries: list[WorklogEntry]) -> str:
    """'By issue' section — hours per issue key, descending by hours."""
    per_issue: dict[str, int] = defaultdict(int)
    for e in entries:
        per_issue[e.issue_key] += e.seconds
    ordered = sorted(per_issue.items(), key=lambda kv: (-kv[1], kv[0]))
    lines = ["By issue (hours, descending):"]
    lines.extend(f"- {key}: {format_seconds_to_human(seconds)}" for key, seconds in ordered)
    return "\n".join(lines)


def _hours_by_day(entries: list[WorklogEntry]) -> str:
    """'By day' section — hours per date, chronological."""
    per_day: dict[date, int] = defaultdict(int)
    undated = 0
    for e in entries:
        if e.day is None:
            undated += e.seconds
            continue
        per_day[e.day] += e.seconds
    lines = ["By day (hours):"]
    lines.extend(
        f"- {day.isoformat()}: {format_seconds_to_human(seconds)}"
        for day, seconds in sorted(per_day.items())
    )
    if undated:
        lines.append(f"- (unknown date): {format_seconds_to_human(undated)}")
    return "\n".join(lines)


def aggregate_sections(
    entries: list[WorklogEntry], *, group_by: str, include_totals: bool
) -> str:
    """Render the requested aggregation sections (empty string for defaults).

    ``group_by`` selects one extra section ("issue" or "day");
    ``include_totals`` appends a "Total:" line. Callers must only invoke
    this when at least one of the two is active — the default invocation
    (none/false) must return the byte-identical pre-P5 response, i.e. no
    sections at all.
    """
    sections: list[str] = []
    if group_by == "issue":
        sections.append(_hours_by_issue(entries))
    elif group_by == "day":
        sections.append(_hours_by_day(entries))
    if include_totals:
        total = sum(e.seconds for e in entries)
        sections.append(f"Total for period: {format_seconds_to_human(total)}")
    return "\n\n".join(sections)


def validate_group_by(value: Any) -> str:
    """Validate the group_by parameter. Raises ValueError on bad input."""
    if not isinstance(value, str) or value not in GROUP_BY_VALUES:
        raise ValueError(
            f"'group_by' must be one of {', '.join(repr(v) for v in GROUP_BY_VALUES)}; "
            f"got {value!r}."
        )
    return value


def validate_include_totals(value: Any) -> bool:
    """Validate the include_totals parameter. Raises ValueError on bad input."""
    if not isinstance(value, bool):
        raise ValueError("'include_totals' must be a boolean (true/false).")
    return value


__all__ = [
    "GROUP_BY_VALUES",
    "WorklogEntry",
    "aggregate_sections",
    "extract_entries",
    "validate_group_by",
    "validate_include_totals",
]
