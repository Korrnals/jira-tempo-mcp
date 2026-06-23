"""Weekly summary template — compact overview without per-issue detail.

Renders total hours, top issues by time, and a short header. Useful for
quick stand-up summaries where the full issue breakdown is not needed.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...config import Config
from ...utils import format_seconds_to_human
from .._shared import extract_issue_key, extract_seconds, format_date, week_range


class WeeklySummaryTemplate:
    """Compact weekly summary (totals + top issues, no per-issue lines)."""

    name: str = "weekly_summary"
    description: str = (
        "Compact weekly summary: total hours, top 5 issues by time, no per-issue detail lines."
    )

    def render(
        self,
        worklogs: list[dict[str, Any]],
        config: Config,
        **kwargs: Any,
    ) -> str:
        """Render a compact weekly summary."""
        from datetime import date

        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        if monday is None or friday is None:
            today = date.today()
            monday, friday = week_range(today)
        issue_titles: dict[str, str] = kwargs.get("issue_titles") or {}

        per_issue: dict[str, int] = defaultdict(int)
        total_seconds = 0
        for wl in worklogs:
            key = extract_issue_key(wl)
            if not key:
                continue
            secs = extract_seconds(wl)
            per_issue[key] += secs
            total_seconds += secs

        lines: list[str] = []
        # UX-7: prefer the ``author`` override (passed when generating
        # a report for a different user via ``username``), else fall back
        # to config.report_author_header.
        author_label = kwargs.get("author") or config.report_author_header
        lines.append(
            f"[{author_label}] Сводка за неделю ({format_date(monday)} - {format_date(friday)}):"
        )
        lines.append("")
        lines.append(f"Всего отработано: {format_seconds_to_human(total_seconds)}")
        lines.append(f"Задач затронуто: {len(per_issue)}")
        lines.append("")

        top = sorted(per_issue.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if top:
            lines.append("Топ-5 задач по времени:")
            for key, secs in top:
                title = issue_titles.get(key, config.section_map.get(key, key))
                lines.append(f"  - {key} ({title}): {format_seconds_to_human(secs)}")
        else:
            lines.append("(нет отработанных задач)")

        return "\n".join(lines).rstrip() + "\n"


__all__ = ["WeeklySummaryTemplate"]
