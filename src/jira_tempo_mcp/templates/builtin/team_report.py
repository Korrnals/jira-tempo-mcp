"""Team report template — per-user sections + aggregate summary.

Renders one section per user (display name or username header) followed by
an aggregate summary with per-user totals and top issues across the team.
Designed to be fed pre-grouped worklogs via the ``users`` kwarg.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...config import Config
from ...utils import format_seconds_to_human
from .._shared import (
    extract_comment,
    extract_issue_key,
    extract_seconds,
    format_date,
    week_range,
)


class TeamReportTemplate:
    """Team report template (per-user sections + aggregate summary)."""

    name: str = "team_report"
    description: str = (
        "Team report: per-user sections with issue breakdown plus an "
        "aggregate summary (per-user totals, grand total, top 5 issues)."
    )

    def render(
        self,
        worklogs: list[dict[str, Any]],
        config: Config,
        **kwargs: Any,
    ) -> str:
        """Render a team report.

        kwargs:
            monday/friday: target week bounds (date). Derived if absent.
            issue_titles: dict[str, str] of pre-resolved issue titles.
            users: ordered list of (username, display_name) tuples. Each user
                with worklogs gets a section; users without worklogs are noted
                in the summary. If absent, a single anonymous section is used.
            per_user_worklogs: dict[str, list[dict]] mapping username -> worklogs.
                If absent, all worklogs are rendered under one section.
        """
        from datetime import date

        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        if monday is None or friday is None:
            today = date.today()
            monday, friday = week_range(today)
        issue_titles: dict[str, str] = kwargs.get("issue_titles") or {}
        users: list[tuple[str, str]] = kwargs.get("users") or []
        per_user_worklogs: dict[str, list[dict[str, Any]]] = kwargs.get("per_user_worklogs") or {}

        lines: list[str] = []
        lines.append(f"Командный отчёт за неделю ({format_date(monday)} - {format_date(friday)}):")
        lines.append("")

        per_user_totals: dict[str, int] = {}
        cross_issue_totals: dict[str, int] = defaultdict(int)
        empty_users: list[str] = []

        for username, display_name in users:
            user_worklogs = per_user_worklogs.get(username, [])
            header = display_name or username
            if not user_worklogs:
                empty_users.append(header)
                per_user_totals[header] = 0
                continue

            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            user_total = 0
            for wl in user_worklogs:
                key = extract_issue_key(wl)
                if not key:
                    continue
                grouped[key].append(wl)
                secs = extract_seconds(wl)
                user_total += secs
                cross_issue_totals[key] += secs
            per_user_totals[header] = user_total

            lines.append(f"== {header} ({format_seconds_to_human(user_total)}) ==")
            # Stable order first, then remaining by time desc.
            used: set[str] = set()
            for key in config.stable_order:
                if key not in grouped:
                    continue
                title = issue_titles.get(key, config.section_map.get(key, key))
                lines.append(f"  - {key} ({title}):")
                for wl in grouped[key]:
                    comment = extract_comment(wl)
                    if comment:
                        lines.append(f"      + {comment}")
                    else:
                        lines.append(f"      + {format_seconds_to_human(extract_seconds(wl))}")
                used.add(key)
            remaining = sorted(
                (k for k in grouped if k not in used),
                key=lambda k: sum(extract_seconds(w) for w in grouped[k]),
                reverse=True,
            )
            for key in remaining:
                title = issue_titles.get(key, key)
                lines.append(f"  - {key} ({title}):")
                for wl in grouped[key]:
                    comment = extract_comment(wl)
                    if comment:
                        lines.append(f"      + {comment}")
                    else:
                        lines.append(f"      + {format_seconds_to_human(extract_seconds(wl))}")
            lines.append("")

        # --- Aggregate summary ---
        grand_total = sum(per_user_totals.values())
        lines.append("== Сводка по команде ==")
        lines.append(f"Всего отработано: {format_seconds_to_human(grand_total)}")
        lines.append("")
        lines.append("По сотрудникам:")
        for header, total in per_user_totals.items():
            lines.append(f"  - {header}: {format_seconds_to_human(total)}")
        if empty_users:
            lines.append("")
            lines.append("Без отработанного времени:")
            for header in empty_users:
                lines.append(f"  - {header}")
        top_issues = sorted(cross_issue_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if top_issues:
            lines.append("")
            lines.append("Топ-5 задач команды:")
            for key, secs in top_issues:
                title = issue_titles.get(key, key)
                lines.append(f"  - {key} ({title}): {format_seconds_to_human(secs)}")

        return "\n".join(lines).rstrip() + "\n"


__all__ = ["TeamReportTemplate"]
