"""Week status aggregation (B2, ArchComm 2026-10-30) — read-only.

Contract §2 item 1: the data window is Mon–Sun of the target week; entries
on Sat/Sun carry the «вне окна рендера» marker (the txt report renders
Mon–Fri only); the weekly norm is a call parameter (default 40h); overtime
is a per-day flag (a day over 8 tracked hours). Pure functions only —
fetching stays in the server handler, so this module never touches
Jira/Tempo.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .templates._shared import extract_seconds, parse_tempo_date
from .utils import format_seconds_to_human

_OVERTIME_THRESHOLD_SECONDS = 8 * 3600

_DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def week_status_text(
    worklogs: list[dict[str, Any]],
    *,
    target: date,
    username: str,
    expected_hours: float = 40.0,
) -> str:
    """Render the read-only week status text (B2).

    ``worklogs`` are raw Tempo worklog dicts for the Mon–Sun window (the
    handler fetches them); entries outside the window are ignored. The
    status is about tracked TIME — issue keys and comments are never
    included, so no worklog content can leak through this tool.
    """
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)

    per_day: dict[date, int] = {}
    for wl in worklogs:
        wl_date = parse_tempo_date(wl.get("started") or wl.get("startDate"))
        if wl_date is None or not (monday <= wl_date <= sunday):
            continue
        per_day[wl_date] = per_day.get(wl_date, 0) + extract_seconds(wl)

    norm_seconds = int(round(expected_hours * 3600))
    lines: list[str] = [
        f"Week status for {username} — {monday.isoformat()} .. {sunday.isoformat()} "
        "(data window Mon–Sun, render window Mon–Fri)",
        f"Norm: {format_seconds_to_human(norm_seconds)} (expected_hours)",
        "",
    ]

    empty_render_days: list[str] = []
    render_total = 0
    weekend_total = 0
    total = 0
    for offset in range(7):
        day = monday + timedelta(days=offset)
        label = f"{_DAY_LABELS[offset]} {day.strftime('%d.%m')}"
        seconds = per_day.get(day, 0)
        total += seconds
        if offset < 5:  # Mon–Fri = render window
            render_total += seconds
            day_value = format_seconds_to_human(seconds) if seconds else "no entries"
            overtime = " [overtime >8h]" if seconds > _OVERTIME_THRESHOLD_SECONDS else ""
            lines.append(f"- {label}: {day_value}{overtime}")
            if not seconds:
                empty_render_days.append(label)
        else:  # Sat–Sun = outside the render window
            weekend_total += seconds
            if seconds:
                lines.append(f"- {label}: {format_seconds_to_human(seconds)} (вне окна рендера)")
            else:
                lines.append(f"- {label}: no entries")

    lines.append("")
    if empty_render_days:
        lines.append("Days without entries (render window): " + ", ".join(empty_render_days))
    lines.append(f"Total Mon–Fri (render window): {format_seconds_to_human(render_total)}")
    lines.append(f"Total Mon–Sun: {format_seconds_to_human(total)}")
    if weekend_total:
        lines.append(
            f"Weekend tracked: {format_seconds_to_human(weekend_total)} (вне окна рендера)"
        )

    remaining = norm_seconds - render_total
    check = (
        f"Norm check: {format_seconds_to_human(render_total)} of "
        f"{format_seconds_to_human(norm_seconds)}"
    )
    if remaining > 0:
        lines.append(f"{check} — {format_seconds_to_human(remaining)} remaining")
    elif remaining == 0:
        lines.append(f"{check} — norm met")
    else:
        lines.append(f"{check} — {format_seconds_to_human(-remaining)} over norm")
    return "\n".join(lines)


__all__ = ["week_status_text"]
