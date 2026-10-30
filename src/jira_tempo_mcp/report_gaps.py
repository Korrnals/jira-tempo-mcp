"""Report gap finder (P8, backlog wave 2026-10-30) — strictly READ-ONLY.

Compares the weeks (ISO, Mon–Fri render window, Mon–Sun data window) in
which a user actually tracked time (hours > 0) against the weekly report
files on disk (recursive glob ``*_<monday>_<friday>.*`` under the report
output root — the same root ``_validate_output_dir`` uses:
``config.report_output_dir``, falling back to ``~/.mcp/jira-tempo-mcp/reports``).

Guarantees:
- no network beyond the two read-only Tempo calls (worker key + one
  worklog search) made by the handler;
- the filesystem is only READ via ``Path.rglob`` inside the report root —
  nothing is written, nothing outside the root is touched;
- the look-back window is capped at ``GAP_WINDOW_WEEKS`` weeks; an older
  ``since`` is clamped (and the clamp is stated in the response).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .templates._shared import parse_tempo_date
from .utils import format_seconds_to_human

GAP_WINDOW_WEEKS = 26


@dataclass(frozen=True)
class WeekGap:
    """One week (with tracked time) and its report-file status."""

    monday: date
    friday: date
    sunday: date
    seconds: int  # Mon–Sun tracked seconds
    covered: bool


def resolve_since(raw: Any, *, today: date) -> tuple[date, bool]:
    """Resolve the ``since`` parameter. Returns (since, was_clamped).

    Default: January 1st of the current year. Any candidate older than
    ``GAP_WINDOW_WEEKS`` weeks (default included — late in the year Jan 1st
    is beyond the cap) is clamped to that boundary; read-only diagnostics
    tool — clamp-and-disclose beats a hard error here.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        since = date(today.year, 1, 1)
    else:
        if not isinstance(raw, str):
            raise ValueError(
                f"'since' must be an ISO date string (YYYY-MM-DD); got {type(raw).__name__}."
            )
        try:
            since = date.fromisoformat(raw)
        except ValueError:
            raise ValueError(f"Invalid since: {raw!r}. Expected ISO format YYYY-MM-DD.") from None
        if since > today:
            raise ValueError(f"'since' {since.isoformat()} is in the future.")
    floor = today - timedelta(weeks=GAP_WINDOW_WEEKS)
    if since < floor:
        return floor, True
    return since, False


def group_hours_by_week(
    worklogs: list[dict[str, Any]], *, window_start: date, window_end: date
) -> dict[date, int]:
    """Sum tracked seconds per ISO week (Mon–Sun) inside the window.

    Returns only weeks with hours > 0, keyed by the week's Monday. The
    data window is Mon–Sun: a Sunday entry counts toward its own week.
    """
    per_week: dict[date, int] = defaultdict(int)
    for wl in worklogs:
        wl_date = parse_tempo_date(wl.get("started") or wl.get("startDate"))
        if wl_date is None or not (window_start <= wl_date <= window_end):
            continue
        seconds = wl.get("timeSpentSeconds", 0)
        if not isinstance(seconds, int) or seconds <= 0:
            continue
        monday = wl_date - timedelta(days=wl_date.weekday())
        per_week[monday] += seconds
    return dict(per_week)


def find_report_file(root: Path, monday: date, friday: date) -> Path | None:
    """Recursively look for ``*_<monday>_<friday>.*`` under ``root``.

    Matches any filename prefix (any username override). Missing root,
    read errors, or no match → None (the week is simply not covered).
    """
    if not root.is_dir():
        return None
    pattern = f"*_{monday.isoformat()}_{friday.isoformat()}.*"
    try:
        for path in root.rglob(pattern):
            if path.is_file():
                return path
    except OSError:
        return None
    return None


def build_week_gaps(
    worklogs: list[dict[str, Any]],
    *,
    root: Path,
    window_start: date,
    window_end: date,
) -> list[WeekGap]:
    """Build the per-week covered/missing list (chronological)."""
    per_week = group_hours_by_week(worklogs, window_start=window_start, window_end=window_end)
    gaps: list[WeekGap] = []
    for monday in sorted(per_week):
        friday = monday + timedelta(days=4)
        sunday = monday + timedelta(days=6)
        covered = find_report_file(root, monday, friday) is not None
        gaps.append(
            WeekGap(
                monday=monday,
                friday=friday,
                sunday=sunday,
                seconds=per_week[monday],
                covered=covered,
            )
        )
    return gaps


def render_week_gaps(
    gaps: list[WeekGap],
    *,
    username: str,
    since: date,
    today: date,
    clamped: bool,
    root: Path,
) -> str:
    """Render the human-readable gap report."""
    lines = [
        f"Report gaps for {username} — {since.isoformat()} .. {today.isoformat()}",
        f"Report dir: {root}",
    ]
    if clamped:
        lines.append(
            f"Note: 'since' was clamped to {since.isoformat()} "
            f"(look-back capped at {GAP_WINDOW_WEEKS} weeks)."
        )
    if not gaps:
        lines.append("No weeks with tracked time found in the window.")
        return "\n".join(lines)
    lines.append("Weeks with tracked time (render window Mon–Fri):")
    for gap in gaps:
        status = "covered" if gap.covered else "MISSING (no report file)"
        lines.append(
            f"- {gap.monday.isoformat()} .. {gap.friday.isoformat()}: "
            f"{format_seconds_to_human(gap.seconds)} tracked — {status}"
        )
    covered_n = sum(1 for g in gaps if g.covered)
    missing_n = len(gaps) - covered_n
    total = format_seconds_to_human(sum(g.seconds for g in gaps))
    summary = f"Summary: {len(gaps)} weeks with tracked time — {covered_n} covered"
    if missing_n:
        summary += f", {missing_n} missing report file(s)"
    summary += f"; total tracked {total}."
    lines.append(summary)
    return "\n".join(lines)


__all__ = [
    "GAP_WINDOW_WEEKS",
    "WeekGap",
    "build_week_gaps",
    "find_report_file",
    "group_hours_by_week",
    "render_week_gaps",
    "resolve_since",
]
