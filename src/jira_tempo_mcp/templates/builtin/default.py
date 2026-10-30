"""Default weekly report template — mirrors the original report.py layout.

Renders worklogs grouped by issue with stable sections, non-issue sections,
and remaining issues sorted by total time descending. This is the backward-
compatible default selected when ``REPORT_TEMPLATE=default`` (or unset).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...config import Config
from ...utils import format_seconds_to_human
from .._shared import (
    drop_lines_matching_title_counted,
    extract_issue_key,
    extract_seconds,
    format_date,
    group_worklogs_by_comment_raw,
    month_ru,
    render_comment_lines,
    week_range,
)


class DefaultTemplate:
    """Default weekly report template (issue-grouped, stable sections).

    Description contract (ArchComm 2026-10-30, slice B1): ``description``
    below documents the canonical rendered form of this builtin template and
    is surfaced to agents via ``list_report_templates``. ANY change to this
    template's rendering MUST be accompanied by an update to ``description``
    in the same commit — the description is the agent-facing contract of the
    output shape, and a stale description is treated as a docs-reality
    regression.
    """

    name: str = "default"
    description: str = (
        "Canonical Komus/Golikhin weekly report — [Голихин Л.С.] Отчет работы "
        "за неделю, Mon–Fri, issue-grouped with stable sections"
    )
    kind: str = "builtin"
    engine: str = "Python"

    def render(
        self,
        worklogs: list[dict[str, Any]],
        config: Config,
        **kwargs: Any,
    ) -> str:
        """Render worklogs to the default weekly report text.

        kwargs:
            monday: optional date — the Monday of the target week. If absent,
                the week is derived from the first worklog date or today.
            friday: optional date — the Friday of the target week.
            issue_titles: optional dict[str, str] — pre-resolved issue titles.
            dropped_lines: optional list[str] — when provided (B4
                ``include_dropped``), collects every line the renderer drops
                as a title echo. Owner-channel data; never logged. When
                absent, drops are collected into a discard list and the
                rendering is byte-identical to the pre-B4 output.
        """
        from datetime import date

        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        if monday is None or friday is None:
            today = date.today()
            monday, friday = week_range(today)
        issue_titles: dict[str, str] = kwargs.get("issue_titles") or {}
        collector: list[str] | None = kwargs.get("dropped_lines")
        discard: list[str] = []
        dropped_sink = collector if collector is not None else discard

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        total_seconds = 0
        for wl in worklogs:
            key = extract_issue_key(wl)
            if not key:
                continue
            grouped[key].append(wl)
            total_seconds += extract_seconds(wl)

        lines: list[str] = []
        # UX-7: prefer the ``author`` override (passed when generating
        # a report for a different user via ``username``), else fall back
        # to config.report_author_header.
        author_label = kwargs.get("author") or config.report_author_header
        lines.append(
            f"[{author_label}] Отчет работы за неделю ({format_date(monday)} - {format_date(friday)}):"
        )
        lines.append("")

        section_num = 1
        used_keys: set[str] = set()

        # 1. Stable sections in defined order.
        for key in config.stable_order:
            if key not in grouped:
                continue
            title = issue_titles.get(key, config.section_map.get(key, key))
            lines.append(f"{section_num}. {title} [{key}]")
            for comment, secs in group_worklogs_by_comment_raw(grouped[key]):
                human = format_seconds_to_human(secs)
                if comment:
                    lines.extend(
                        render_comment_lines(
                            drop_lines_matching_title_counted(comment, title, dropped_sink),
                            indent="\t",
                            marker="+",
                            time_human=human,
                        )
                    )
                else:
                    lines.append(f"\t+ {human} отработано")
            lines.append("")
            used_keys.add(key)
            section_num += 1

        # 2. Non-issue sections (planerki, Jira work) — always present.
        for title in config.non_issue_sections:
            lines.append(f"{section_num}. {title}")
            lines.append("")
            section_num += 1

        # 3. Remaining project tasks, sorted by total time desc.
        remaining = [k for k in grouped if k not in used_keys]
        remaining.sort(key=lambda k: sum(extract_seconds(w) for w in grouped[k]), reverse=True)
        for key in remaining:
            title = issue_titles.get(key, key)
            # Header for non-stable sections: the key already appears in the
            # leading [KEY] bracket, so the bare second occurrence was a
            # duplicate (and collided with the title when they matched).
            lines.append(f'{section_num}. [{key}] - "{title}"')
            for comment, secs in group_worklogs_by_comment_raw(grouped[key]):
                human = format_seconds_to_human(secs)
                if comment:
                    lines.extend(
                        render_comment_lines(
                            drop_lines_matching_title_counted(comment, title, dropped_sink),
                            indent="\t",
                            marker="+",
                            time_human=human,
                        )
                    )
                else:
                    lines.append(f"\t+ {human} отработано")
            lines.append("")
            section_num += 1

        return "\n".join(lines).rstrip() + "\n"


__all__ = ["DefaultTemplate", "month_ru"]
